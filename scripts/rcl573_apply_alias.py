"""
rcl573_components.csv(153행, 원본 — 수정하지 않음)에 사용자 확정본
supplier_alias.csv를 조인하고, 한 셀에 여러 부품번호가 섞여 있던 문제를
rcl573_shared_parts.py에서 이미 검증한 정규식 토큰 추출로 "부품번호 1개 = 1행"으로
분해해 rcl573_components_normalized.csv를 만든다.

part_number 분해 규칙:
- 빈 셀 → 그대로 1행, part_number=''.
- 정규식으로 토큰이 1개 이상 뽑히면 → 토큰마다 1행(그 외 컬럼은 원행 그대로 복제).
- 정규식으로 토큰이 하나도 안 뽑히는데 셀이 비어있지 않은 경우(3건 실측 확인 —
  "282402S304"·"91150-R5***"·"91850R6020" — 구분자 누락/와일드카드로 정상 패턴에서
  벗어난 단일 값들) → 여러 값이 섞인 게 아니라 그 자체로 하나의 값이므로 분해하지
  않고 원문 그대로 1행 유지(정보 손실 방지, 지어내지 않음).

supplier_group=EXCLUDE(Not Applicable/TBD)인 행은 supplier_canonical·supplier_group을
빈값 처리 — 행 자체는 삭제하지 않는다. alias에 없는 raw_name은 임의로 채우지 않고
콘솔에 목록으로 보고한다.
"""
import csv
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENTS_CSV = REPO_ROOT / "data" / "processed" / "rcl573_components.csv"
ALIAS_CSV = REPO_ROOT / "data" / "processed" / "supplier_alias.csv"
OUT_CSV = REPO_ROOT / "data" / "processed" / "rcl573_components_normalized.csv"

PART_TOKEN_RE = re.compile(r"\b([A-Za-z0-9]{5})[- ]([A-Za-z0-9]{3,10})\b")


def extract_part_tokens(cell: str) -> list[str]:
    """중복 제거된 "PREFIX-SUFFIX" 토큰 리스트(등장 순서 보존)."""
    seen = []
    for m in PART_TOKEN_RE.finditer(cell):
        tok = f"{m.group(1)}-{m.group(2)}"
        if tok not in seen:
            seen.append(tok)
    return seen


def load_alias() -> dict[str, dict]:
    alias = {}
    with open(ALIAS_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            alias[row["raw_name"]] = {
                "canonical_name": row["canonical_name"],
                "supplier_group": row["supplier_group"],
            }
    return alias


def build():
    with open(COMPONENTS_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0].keys())

    alias = load_alias()
    missing_raw_names = set()

    out_fieldnames = fieldnames + ["supplier_canonical", "supplier_group"]
    out_rows = []

    n_decomposed_source_rows = 0
    n_unparsed_single = 0
    n_blank = 0

    for row in rows:
        supplier_name = (row.get("supplier_name") or "").strip()
        if not supplier_name:
            supplier_canonical, supplier_group = "", ""
        elif supplier_name in alias:
            entry = alias[supplier_name]
            if entry["supplier_group"] == "EXCLUDE":
                supplier_canonical, supplier_group = "", ""
            else:
                supplier_canonical, supplier_group = entry["canonical_name"], entry["supplier_group"]
        else:
            missing_raw_names.add(supplier_name)
            supplier_canonical, supplier_group = "", ""

        cell = (row.get("part_number") or "").strip()
        if not cell:
            n_blank += 1
            part_numbers = [""]
        else:
            tokens = extract_part_tokens(cell)
            if not tokens:
                n_unparsed_single += 1
                part_numbers = [cell]
            else:
                if len(tokens) > 1:
                    n_decomposed_source_rows += 1
                part_numbers = tokens

        for pn in part_numbers:
            new_row = dict(row)
            new_row["part_number"] = pn
            new_row["supplier_canonical"] = supplier_canonical
            new_row["supplier_group"] = supplier_group
            out_rows.append(new_row)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"[ok] {len(rows)}행(원본) -> {len(out_rows)}행(분해 후) -> {OUT_CSV}")
    print(f"[info] 원본 중 part_number 공백 {n_blank}행 / 정규식 미매치(단일값 그대로 유지) {n_unparsed_single}행 / 다중값 분해 대상 {n_decomposed_source_rows}행")

    if missing_raw_names:
        print(f"[WARN] supplier_alias.csv에 없는 raw_name {len(missing_raw_names)}건 (빈값 처리됨, 목록):")
        for name in sorted(missing_raw_names):
            print(f"    - {name!r}")
    else:
        print("[verify] supplier_alias.csv 커버리지: rcl573_components.csv의 모든 supplier_name이 alias에 존재")

    # 다중값 잔존 여부 확인
    residual_multi = [r for r in out_rows if r["part_number"] and len(extract_part_tokens(r["part_number"])) > 1]
    print(f"[verify] part_number 1행 다중값 잔존: {len(residual_multi)}건")

    n_supplier_missing = sum(1 for r in out_rows if not r["supplier_canonical"])
    print(f"[verify] supplier_canonical 결측률: {n_supplier_missing}/{len(out_rows)} ({n_supplier_missing/len(out_rows):.1%})")

    ref = next((r for r in out_rows if r["campaign"] == "24V757000"), None)
    if ref:
        ok_pn = ref["part_number"] == "940C3-DO010"
        ok_can = ref["supplier_canonical"] == "Hyundai Mobis"
        ok_grp = ref["supplier_group"] == "Hyundai Mobis"
        print(f"[verify] 24V757000 기준행: part_number={ref['part_number']}({ok_pn}), supplier_canonical={ref['supplier_canonical']}({ok_can}), supplier_group={ref['supplier_group']}({ok_grp})")
    else:
        print("[verify] 24V757000 행 없음 — 확인 불가")

    return out_rows


if __name__ == "__main__":
    build()
