"""
Part 573 리콜 데이터 수집 1단계.

두 소스를 분리해서 수집한다:
1) NHTSA 리콜 벌크 플랫파일(FLAT_RCL_POST_2010.zip) — 캠페인×부품 단위로
   부품명/부품번호/FMVSS/대수/결함요약/시정요약이 이미 구조화되어 있어
   PDF 파싱 없이 바로 얻을 수 있다. data/raw/에는 쓰지 않는다(CLAUDE.md 금지
   — 이 파일은 스크래치 디렉터리에서 처리 후 버린다).
2) Part 573 PDF 원문 — 공급사명/공급국가/corrected_in_production 체크박스는
   플랫파일에 없어 PDF가 필요하다. NHTSA 공식 API에는 PDF URL 필드가 없고
   nhtsa.gov 상세페이지는 봇 차단(403)이라, 검색엔진이 이미 인덱싱한 실제
   URL을 rcl573_pdf_urls.csv(campaign,pdf_url)로 미리 확보해두고 그 목록을
   그대로 다운로드만 한다(무작위 대입 없음).

CLAUDE.md 원칙: data/raw/ 쓰기 금지, 대용량 파일 청크 처리, latin-1 인코딩 주의.
"""
import csv
import os
import sys
import time
import zipfile
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRATCH_DIR = Path(os.environ.get("RCL573_SCRATCH", r"C:\Users\wnwls\AppData\Local\Temp\claude\C--code-vehicle-defect-agent\aef04fdc-e0ef-48ed-932a-0e1ea841841a\scratchpad"))
FLAT_RCL_URL = "https://static.nhtsa.gov/odi/ffdd/rcl/FLAT_RCL_POST_2010.zip"
FLAT_RCL_ZIP = SCRATCH_DIR / "FLAT_RCL_POST_2010.zip"
FLAT_RCL_TXT = SCRATCH_DIR / "FLAT_RCL_POST_2010.txt"

CANDIDATES_CSV = REPO_ROOT / "data" / "recalls" / "recalls_sw_candidates.csv"
PDF_URLS_CSV = REPO_ROOT / "data" / "processed" / "rcl573_pdf_urls.csv"
PDF_DIR = REPO_ROOT / "docs" / "rcl573"
FLATFILE_OUT = REPO_ROOT / "data" / "processed" / "rcl573_flatfile_components.csv"
FETCH_LOG = REPO_ROOT / "data" / "processed" / "rcl573_fetch_log.csv"

UA = "vehicle-defect-agent-research/1.0 (contact: wnwlsgml0112@gmail.com)"

# FLAT_RCL 필드 순서 (RCL.txt 스펙, 1-indexed 그대로 0-indexed 리스트로)
RCL_COLS = [
    "RECORD_ID", "CAMPNO", "MAKETXT", "MODELTXT", "YEARTXT", "MFGCAMPNO",
    "COMPNAME", "MFGNAME", "BGMAN", "ENDMAN", "RCLTYPECD", "POTAFF",
    "ODATE", "INFLUENCED_BY", "MFGTXT", "RCDATE", "DATEA", "RPNO",
    "FMVSS", "DESC_DEFECT", "CONEQUENCE_DEFECT", "CORRECTIVE_ACTION",
    "NOTES", "RCL_CMPT_ID", "MFR_COMP_NAME", "MFR_COMP_DESC",
    "MFR_COMP_PTNO", "DO_NOT_DRIVE", "PARK_OUTSIDE",
]


def load_campaigns() -> list[str]:
    with open(CANDIDATES_CSV, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        campaigns = sorted({row["NHTSACampaignNumber"].strip() for row in reader})
    return campaigns


def download_flat_rcl():
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    if FLAT_RCL_TXT.exists():
        print(f"[skip] {FLAT_RCL_TXT} 이미 존재")
        return
    print(f"[download] {FLAT_RCL_URL}")
    resp = requests.get(FLAT_RCL_URL, headers={"User-Agent": UA}, stream=True, timeout=120)
    resp.raise_for_status()
    with open(FLAT_RCL_ZIP, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)
    with zipfile.ZipFile(FLAT_RCL_ZIP) as zf:
        zf.extractall(SCRATCH_DIR)
    print(f"[ok] extracted to {FLAT_RCL_TXT}")


OUT_COLS = [
    "CAMPNO", "MFGCAMPNO", "MFGTXT", "POTAFF", "RCDATE", "ODATE",
    "COMPNAME", "MFR_COMP_NAME", "MFR_COMP_PTNO", "MFR_COMP_DESC",
    "FMVSS", "RPNO", "DESC_DEFECT", "CONEQUENCE_DEFECT", "CORRECTIVE_ACTION",
    "NOTES", "DO_NOT_DRIVE", "PARK_OUTSIDE", "affected_models",
]


def filter_flat_rcl(campaigns: set[str]):
    """대용량(약 300MB) 파일을 한 줄씩 스트리밍 처리 — 메모리 전체 로드 금지.

    원본은 캠페인×모델×연식×부품 단위라 같은 부품이 여러 모델/연식에 걸쳐
    중복 등장한다(예: 26V046000이 실제로 8개 서로 다른 부품을 갖되, 모델×연식
    조합 수만큼 반복돼 84행으로 나타남). 부품 단위(CAMPNO, MFR_COMP_NAME,
    MFR_COMP_PTNO)로 dedupe하고, 영향 모델 목록만 별도 컬럼에 집계한다.
    """
    raw_rows = []
    with open(FLAT_RCL_TXT, encoding="latin-1", newline="") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        for parts in reader:
            if len(parts) < 2:
                continue
            campno = parts[1].strip()
            if campno in campaigns:
                row = dict(zip(RCL_COLS, parts + [""] * (len(RCL_COLS) - len(parts))))
                raw_rows.append(row)

    dedup: dict[tuple, dict] = {}
    models_by_key: dict[tuple, set] = {}
    for row in raw_rows:
        key = (row["CAMPNO"], row["MFR_COMP_NAME"].strip(), row["MFR_COMP_PTNO"].strip())
        models_by_key.setdefault(key, set()).add(f"{row['MODELTXT'].strip()} {row['YEARTXT'].strip()}")
        if key not in dedup:
            dedup[key] = row

    out_rows = []
    for key, row in dedup.items():
        out = {col: row.get(col, "") for col in OUT_COLS if col != "affected_models"}
        out["affected_models"] = "; ".join(sorted(models_by_key[key]))
        out_rows.append(out)
    out_rows.sort(key=lambda r: (r["CAMPNO"], r["MFR_COMP_PTNO"]))

    FLATFILE_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(FLATFILE_OUT, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_COLS)
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"[ok] 원본 {len(raw_rows)}행 -> 부품 dedupe {len(out_rows)}행 -> {FLATFILE_OUT}")
    found_campaigns = {r["CAMPNO"] for r in out_rows}
    missing = campaigns - found_campaigns
    print(f"[check] 매칭된 캠페인 {len(found_campaigns)}/{len(campaigns)}개, 누락 {len(missing)}개")
    if missing:
        print(f"[check] 누락 목록: {sorted(missing)}")
    return out_rows


def download_pdfs():
    if not PDF_URLS_CSV.exists():
        print(f"[skip] {PDF_URLS_CSV} 없음 — PDF URL 매핑을 먼저 준비해야 함")
        return
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    log_rows = []
    with open(PDF_URLS_CSV, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        entries = list(reader)

    for i, row in enumerate(entries):
        campaign = row["campaign"].strip()
        url = row.get("pdf_url", "").strip()
        if not url:
            log_rows.append({"campaign": campaign, "status": "no_url", "pdf_url": "", "local_path": ""})
            continue
        ext = ".pdf"
        local_path = PDF_DIR / f"{campaign}{ext}"
        if local_path.exists():
            log_rows.append({"campaign": campaign, "status": "already_exists", "pdf_url": url, "local_path": str(local_path)})
            continue
        try:
            resp = requests.get(url, headers={"User-Agent": UA}, timeout=60)
            resp.raise_for_status()
            if resp.headers.get("Content-Type", "").lower().startswith("application/pdf") or resp.content[:4] == b"%PDF":
                local_path.write_bytes(resp.content)
                log_rows.append({"campaign": campaign, "status": "ok", "pdf_url": url, "local_path": str(local_path)})
            else:
                log_rows.append({"campaign": campaign, "status": "not_pdf", "pdf_url": url, "local_path": ""})
        except Exception as e:
            log_rows.append({"campaign": campaign, "status": f"error:{e}", "pdf_url": url, "local_path": ""})
        time.sleep(1.0)
        if (i + 1) % 10 == 0:
            print(f"[progress] {i+1}/{len(entries)}")

    with open(FETCH_LOG, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["campaign", "status", "pdf_url", "local_path"])
        writer.writeheader()
        writer.writerows(log_rows)

    ok = sum(1 for r in log_rows if r["status"] in ("ok", "already_exists"))
    print(f"[ok] PDF 다운로드 {ok}/{len(log_rows)}건 성공 -> {FETCH_LOG}")


def main():
    campaigns = load_campaigns()
    print(f"[info] 대상 캠페인 {len(campaigns)}개")

    step = sys.argv[1] if len(sys.argv) > 1 else "all"

    if step in ("flatfile", "all"):
        download_flat_rcl()
        filter_flat_rcl(set(campaigns))

    if step in ("pdfs", "all"):
        download_pdfs()


if __name__ == "__main__":
    main()
