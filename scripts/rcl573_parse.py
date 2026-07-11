"""
Part 573 리콜 데이터 수집 2단계 — PDF에서 부품 지식 레이어의 나머지 필드를 뽑아
플랫파일 기반 CSV(rcl573_flatfile_components.csv)와 병합한다.

부품명·부품번호·FMVSS·대수·결함요약·시정요약은 이미 플랫파일(1단계, rcl573_fetch.py)에
구조화되어 있으므로 PDF에서 다시 추출하지 않는다. PDF에서만 얻을 수 있는 필드만 뽑는다:
  - supplier_name, supplier_country ("Component Manufacturer"/"Supplier Identification" 블록)
  - corrected_in_production (verbatim, "Identify How/When ... Corrected in Production" 문단)
  - chronology_attached (bool) — 별첨 PDF를 가리키는 문구("See attached document...")가 있는지만 확인.
    이번 범위에서는 별첨 자체의 URL을 찾지 못함(임베드된 하이퍼링크 없음, 3건 샘플로 확인) —
    URL 필드는 비워두고 존재 여부만 기록.
  - pdf_url (rcl573_pdf_urls.csv에서 그대로)

PDF 서식이 연도별로 다르다(2019~2020년대 초 구서식 vs 2026년 신서식 — 필드 순서·페이지
나뉨 위치가 다름). 페이지 경계마다 반복되는 상용구("The information contained in this
report was submitted pursuant to 49 CFR..." / "Page N of M" / 보고서 제목 라인)를 먼저
제거해 텍스트를 이어붙인 뒤 정규식으로 블록을 찾는다. 실패 시 빈 값으로 두고 결측률로만
보고한다(CLAUDE.md 원칙 — 결측을 오류로 처리하지 않음).
"""
import csv
import re
from pathlib import Path

import pdfplumber

REPO_ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = REPO_ROOT / "docs" / "rcl573"
PDF_URLS_CSV = REPO_ROOT / "data" / "processed" / "rcl573_pdf_urls.csv"
FLATFILE_CSV = REPO_ROOT / "data" / "processed" / "rcl573_flatfile_components.csv"
OUT_CSV = REPO_ROOT / "data" / "processed" / "rcl573_components.csv"
COVERAGE_CSV = REPO_ROOT / "data" / "processed" / "rcl573_coverage_check.csv"

BOILERPLATE_PATTERNS = [
    re.compile(r"The information contained in this report was submitted pursuant to 49 CFR.*", re.IGNORECASE),
    re.compile(r"^Page \d+ of \d+\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Part 573 Safety Recall Report [\w-]+\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^OMB Control No\.?:?\s*2127-0004\s*$", re.IGNORECASE | re.MULTILINE),
]

SECTION_BOUNDARY = re.compile(
    r"(Involved Components|Chronology\s*:?|Description of Remedy|Recall Schedule|Reimbursement Plan|Related NHTSA Recall Number)",
    re.IGNORECASE,
)


def clean_text(text: str) -> str:
    for pat in BOILERPLATE_PATTERNS:
        text = pat.sub("", text)
    return text


def extract_pdf_text(pdf_path: Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        parts = [page.extract_text() or "" for page in pdf.pages]
    return clean_text("\n".join(parts))


def _find_split_x(words: list[dict], page_width: float) -> float:
    """Description of Remedy 절은 라벨(좌)|값(우) 2열 표라, extract_text()가 같은
    y좌표의 라벨·값 텍스트를 한 줄로 섞어버린다(예: 'Identify How/When Recall
    Condition The condition was caused by...'). 페이지별 동적 간격 탐지는 주소/우편번호
    등 다른 열 배치에 흔들려 오탐이 잦았음(19V594000 실측 확인) — 대신 두 표본
    (24V757000·19V594000)에서 값열이 항상 x0≈214pt(US Letter 612pt 폭 기준
    ≈0.343)에서 시작하는 것을 실측으로 확인, 고정 비율을 그대로 사용."""
    return page_width * 0.343


def extract_two_column_rows(page) -> list[tuple[str, str]]:
    """페이지를 (라벨열 텍스트, 값열 텍스트) 행 목록으로 재구성."""
    words = page.extract_words()
    if not words:
        return []
    split_x = _find_split_x(words, page.width)
    rows_by_top: list[tuple[float, list[dict]]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows_by_top and abs(w["top"] - rows_by_top[-1][0]) <= 2.5:
            rows_by_top[-1][1].append(w)
        else:
            rows_by_top.append((w["top"], [w]))
    result = []
    for _, row_words in rows_by_top:
        left = " ".join(w["text"] for w in row_words if w["x0"] < split_x)
        right = " ".join(w["text"] for w in row_words if w["x0"] >= split_x)
        result.append((left, right))
    return result


def extract_two_column_field(all_rows: list[tuple[str, str]], label_regexes: list[re.Pattern]) -> str:
    """label_regexes[0]이 자기 행의 라벨(빈 문자열이 아님)에 매치하는 행을 시작점으로
    삼고, 그 뒤 몇 행 안에서 label_regexes[-1]까지 이어지면(라벨이 여러 행으로
    쪼개진 경우) 시작행부터 값을 이어붙인다. 다음 비어있지 않은 라벨행이 나오면 중단."""
    n = len(all_rows)
    for i in range(n):
        if not all_rows[i][0].strip() or not label_regexes[0].search(all_rows[i][0]):
            continue
        last_label_row = None
        for j in range(i, min(i + 3, n)):
            if label_regexes[-1].search(all_rows[j][0]):
                last_label_row = j
                break
        if last_label_row is None:
            continue
        values = []
        for j in range(i, n):
            label, value = all_rows[j]
            if j > last_label_row and label.strip():
                break
            if value.strip():
                values.append(value.strip())
        return re.sub(r"\s+", " ", " ".join(values)).strip()
    return ""


def extract_supplier_block(text: str) -> tuple[str, str]:
    anchor = re.search(r"Component\s+Manufacturer", text, re.IGNORECASE)
    if not anchor:
        anchor = re.search(r"Supplier\s+Identification", text, re.IGNORECASE)
    if not anchor:
        return "", ""
    rest = text[anchor.end():]
    boundary = SECTION_BOUNDARY.search(rest)
    block = rest[: boundary.start()] if boundary else rest[:800]

    name_m = re.search(r"\bName\s*:\s*(.+)", block)
    country_m = re.search(r"\bCountry\s*:\s*(.+)", block)
    supplier_name = name_m.group(1).strip() if name_m else ""
    supplier_country = country_m.group(1).strip() if country_m else ""
    return supplier_name, supplier_country


CORRECTED_IN_PRODUCTION_LABEL = re.compile(r"[Cc]orrected\s+in\s+[Pp]roduction\s*:?")


def extract_corrected_in_production(text: str, pdf=None) -> str:
    """신서식(단일열)은 정규식으로 바로 잡히지만, 구서식(2열 표, 예: 24V757000·
    19V594000)은 라벨·값이 같은 줄에 섞여 나와 정규식이 실패한다 — 그 경우
    pdf 객체가 주어지면 좌표 기반 2열 재구성(extract_two_column_rows)으로 재시도."""
    m = re.search(
        r"Identify\s+[Hh]ow/[Ww]hen\s+[Rr]ecall\s+[Cc]ondition\s+was\s+[Cc]orrected\s+in\s+[Pp]roduction\s*:?\s*(.+?)"
        r"(?=Recall Schedule|Reimbursement Plan|Description of [Rr]ecall [Ss]chedule|$)",
        text,
        re.DOTALL,
    )
    if m and m.group(1).strip():
        return re.sub(r"\s+", " ", m.group(1)).strip()

    if pdf is None:
        return ""
    label_regexes = [re.compile(r"Identify\s+How/When\s+Recall\s+Condition", re.IGNORECASE), CORRECTED_IN_PRODUCTION_LABEL]
    for page in pdf.pages:
        if "Description of Remedy" not in (page.extract_text() or "") and "Remedy" not in (page.extract_text() or ""):
            continue
        rows = extract_two_column_rows(page)
        value = extract_two_column_field(rows, label_regexes)
        if value:
            return value
    return ""


def extract_chronology(text: str) -> tuple[bool, str]:
    m = re.search(
        r"Chronology\s*:?\s*(.+?)(?=Description of Remedy|Related NHTSA Recall Number|Remedy Type\s*:|$)",
        text,
        re.DOTALL,
    )
    if not m:
        return False, ""
    block = re.sub(r"\s+", " ", m.group(1)).strip()
    attached = bool(re.search(r"see attached", block, re.IGNORECASE))
    return attached, block[:300]


def load_pdf_urls() -> dict[str, str]:
    urls = {}
    if PDF_URLS_CSV.exists():
        with open(PDF_URLS_CSV, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("found", "").strip().lower() == "true" and row.get("pdf_url", "").strip():
                    urls[row["campaign"].strip()] = row["pdf_url"].strip()
    return urls


def parse_all_pdfs() -> dict[str, dict]:
    results = {}
    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    for pdf_path in pdf_files:
        campaign = pdf_path.stem
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text = clean_text("\n".join(page.extract_text() or "" for page in pdf.pages))
                supplier_name, supplier_country = extract_supplier_block(text)
                corrected = extract_corrected_in_production(text, pdf=pdf)
                chrono_attached, chrono_note = extract_chronology(text)
        except Exception as e:
            results[campaign] = {"parse_error": str(e)}
            continue
        results[campaign] = {
            "supplier_name": supplier_name,
            "supplier_country": supplier_country,
            "corrected_in_production": corrected,
            "chronology_attached": chrono_attached,
            "chronology_note": chrono_note,
            "chronology_url": "",  # 임베드된 하이퍼링크 없음(3건 샘플 확인) — 있으면 채움
            "parse_error": "",
        }
    return results


OUT_COLS = [
    "campaign", "mfr_recall_no", "population", "component_name", "component_desc",
    "part_number", "supplier_name", "supplier_country", "defect_cause", "fmvss",
    "remedy_type", "corrected_in_production", "chronology_attached", "chronology_note",
    "chronology_url", "pdf_url", "affected_models",
]


def build_final_csv(pdf_results: dict[str, dict], pdf_urls: dict[str, str]):
    with open(FLATFILE_CSV, encoding="utf-8-sig") as f:
        flat_rows = list(csv.DictReader(f))

    out_rows = []
    for row in flat_rows:
        campaign = row["CAMPNO"]
        pdf = pdf_results.get(campaign, {})
        out_rows.append({
            "campaign": campaign,
            "mfr_recall_no": row.get("MFGCAMPNO", ""),
            "population": row.get("POTAFF", ""),
            "component_name": row.get("MFR_COMP_NAME", ""),
            "component_desc": row.get("MFR_COMP_DESC", ""),
            "part_number": row.get("MFR_COMP_PTNO", ""),
            "supplier_name": pdf.get("supplier_name", ""),
            "supplier_country": pdf.get("supplier_country", ""),
            "defect_cause": row.get("DESC_DEFECT", ""),
            "fmvss": row.get("FMVSS", ""),
            "remedy_type": row.get("CORRECTIVE_ACTION", ""),
            "corrected_in_production": pdf.get("corrected_in_production", ""),
            "chronology_attached": pdf.get("chronology_attached", ""),
            "chronology_note": pdf.get("chronology_note", ""),
            "chronology_url": pdf.get("chronology_url", ""),
            "pdf_url": pdf_urls.get(campaign, ""),
            "affected_models": row.get("affected_models", ""),
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_COLS)
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"[ok] {len(out_rows)}행 -> {OUT_CSV}")
    return out_rows


def verify(out_rows: list[dict], pdf_results: dict[str, dict], pdf_urls: dict[str, str]):
    total_campaigns = len({r["campaign"] for r in out_rows})
    n_pdf_ok = sum(1 for c, r in pdf_results.items() if not r.get("parse_error"))
    n_pdf_error = sum(1 for r in pdf_results.values() if r.get("parse_error"))
    print(f"[verify] PDF 파싱 성공 {n_pdf_ok}건 / 실패 {n_pdf_error}건 (다운로드된 PDF 기준)")
    print(f"[verify] PDF URL 확보 캠페인 {len(pdf_urls)}/{total_campaigns}")

    ref = next((r for r in out_rows if r["campaign"] == "24V757000"), None)
    if ref:
        ok_part = ref["part_number"] == "940C3-DO010"
        ok_supplier = ref["supplier_name"] == "Hyundai Mobis"
        print(f"[verify] 24V757000 기준행 일치: part_number={ok_part}({ref['part_number']}), supplier_name={ok_supplier}({ref['supplier_name']})")
    else:
        print("[verify] 24V757000 행 없음 — 확인 불가")

    def missing_rate(field):
        vals = [r[field] for r in out_rows]
        return sum(1 for v in vals if not str(v).strip()) / len(vals) if vals else 0.0

    for field in ["part_number", "supplier_name", "supplier_country", "corrected_in_production"]:
        print(f"[verify] {field} 결측률: {missing_rate(field):.1%}")

    campaigns_hk = set()
    hk_csv = REPO_ROOT / "data" / "recalls" / "recalls_hk_by_vehicle.csv"
    if hk_csv.exists():
        with open(hk_csv, encoding="utf-8-sig") as f:
            campaigns_hk = {row["NHTSACampaignNumber"].strip() for row in csv.DictReader(f)}
    our_campaigns = {r["campaign"] for r in out_rows}
    overlap = our_campaigns & campaigns_hk
    print(f"[verify] recalls_hk_by_vehicle.csv 조인 커버리지: {len(overlap)}/{len(our_campaigns)}개 캠페인 매칭")

    with open(COVERAGE_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        writer.writerow(["pdf_parse_ok", n_pdf_ok])
        writer.writerow(["pdf_parse_error", n_pdf_error])
        writer.writerow(["pdf_url_found", len(pdf_urls)])
        writer.writerow(["total_campaigns", total_campaigns])
        writer.writerow(["part_number_missing_rate", round(missing_rate("part_number"), 4)])
        writer.writerow(["supplier_name_missing_rate", round(missing_rate("supplier_name"), 4)])
        writer.writerow(["supplier_country_missing_rate", round(missing_rate("supplier_country"), 4)])
        writer.writerow(["corrected_in_production_missing_rate", round(missing_rate("corrected_in_production"), 4)])
        writer.writerow(["hk_by_vehicle_join_coverage", f"{len(overlap)}/{len(our_campaigns)}"])
    print(f"[ok] 검증 요약 -> {COVERAGE_CSV}")


def main():
    pdf_urls = load_pdf_urls()
    pdf_results = parse_all_pdfs()
    out_rows = build_final_csv(pdf_results, pdf_urls)
    verify(out_rows, pdf_results, pdf_urls)


if __name__ == "__main__":
    main()
