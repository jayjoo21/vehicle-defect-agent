"""
rcl573_components.csv에서 여러 캠페인·차종에 걸쳐 등장하는 부품 계열(part_family)을
찾아 shared_parts.csv로 집계한다. "같은 부품"이 아니라 "같은 부품 계열"이다 —
부품번호가 같은 5자리로 시작해도 그 안에서 SW 버전·사양이 다를 수 있다.

part_number 필드 실측 결과, 앞 5자리를 단순히 슬라이스하는 방식은 위험하다는 것을
확인했다: 한 칸에 여러 부품번호가 세미콜론/슬래시/쉼표/&로 뒤섞여 있거나("940C3-PI010;
940C3-PI020; 940C3-PI000", "[[[ 58920-J5070 & 58920-J5170 ]]]"), 차종명이 앞에
붙어 있거나("Telluride: 94051-S9000", "Sportage HECU: 58920-D9100 / Cadenza
HECU: 58920-F6210" — 이 경우 차종명 자체에 "/"가 포함돼 구분자 기준 split이 위험),
공백 구분 부품번호(다이얼/스위치류, "C6061 ADUS0")도 섞여 있다.

그래서 구분자를 해석해 split하는 대신, 셀 전체에서 "5자리 영숫자 + 구분자(-  또는
공백) + 3~10자리 영숫자" 형태의 부품번호처럼 보이는 토큰을 정규식으로 전부 찾아내는
방식을 쓴다 — 어떤 구분자·접두사가 붙어 있어도 실제 부품번호 토큰만 안정적으로
뽑힌다(차종명 단어는 5글자 정확히 일치해야 매치되므로 오탐 거의 없음, 검증 결과
아래 참조).
"""
import csv
import re
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENTS_CSV = REPO_ROOT / "data" / "processed" / "rcl573_components.csv"
HK_BY_VEHICLE_CSV = REPO_ROOT / "data" / "recalls" / "recalls_hk_by_vehicle.csv"
OUT_CSV = REPO_ROOT / "data" / "processed" / "shared_parts.csv"

PART_TOKEN_RE = re.compile(r"\b([A-Za-z0-9]{5})[- ]([A-Za-z0-9]{3,10})\b")


def extract_part_tokens(cell: str) -> list[tuple[str, str]]:
    """(family, full_token) 튜플 리스트. family는 대문자 5자리."""
    out = []
    for m in PART_TOKEN_RE.finditer(cell):
        family = m.group(1).upper()
        token = f"{m.group(1)}-{m.group(2)}"
        out.append((family, token))
    return out


def load_campaign_models() -> dict[str, set[str]]:
    campaign_models: dict[str, set[str]] = defaultdict(set)
    with open(HK_BY_VEHICLE_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            campaign_models[row["NHTSACampaignNumber"].strip()].add(row["Model"].strip())
    return campaign_models


def build():
    with open(COMPONENTS_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    campaign_models = load_campaign_models()

    n_blank = 0
    n_no_token_found = 0
    n_multi_family_rows = 0

    family_data = defaultdict(lambda: {
        "component_names": defaultdict(int),
        "part_numbers": set(),
        "campaigns": set(),
        "supplier_names": set(),
    })

    for row in rows:
        cell = (row.get("part_number") or "").strip()
        if not cell:
            n_blank += 1
            continue
        tokens = extract_part_tokens(cell)
        if not tokens:
            n_no_token_found += 1
            continue
        families_in_row = {fam for fam, _ in tokens}
        if len(families_in_row) > 1:
            n_multi_family_rows += 1

        for fam in families_in_row:
            fd = family_data[fam]
            comp_name = (row.get("component_name") or "").strip()
            if comp_name:
                fd["component_names"][comp_name] += 1
            for f2, tok in tokens:
                if f2 == fam:
                    fd["part_numbers"].add(tok)
            fd["campaigns"].add(row["campaign"])
            sup = (row.get("supplier_name") or "").strip()
            if sup:
                fd["supplier_names"].add(sup)

    out_rows = []
    for fam, fd in family_data.items():
        models: set[str] = set()
        for camp in fd["campaigns"]:
            models |= campaign_models.get(camp, set())
        campaign_count = len(fd["campaigns"])
        model_count = len(models)
        if campaign_count < 2 and model_count < 2:
            continue
        # 대표 이름 동률일 때 대괄호로 감싸인 표기(예: "[[[ HECU ]]]")보다
        # 깨끗한 표기(예: "HECU")를 우선한다 — 원본 데이터 자체는 안 건드림,
        # 이 대표값은 순전히 사람이 훑어볼 때 쓰는 표시용 컬럼이라 가독성 우선.
        component_rep = ""
        if fd["component_names"]:
            component_rep = sorted(
                fd["component_names"].items(),
                key=lambda kv: (-kv[1], bool(re.search(r"[\[\]{}]", kv[0])), kv[0]),
            )[0][0]
        out_rows.append({
            "part_family": fam,
            "component_name_대표": component_rep,
            "part_numbers": "; ".join(sorted(fd["part_numbers"])),
            "campaigns": "; ".join(sorted(fd["campaigns"])),
            "models": "; ".join(sorted(models)),
            "campaign_count": campaign_count,
            "model_count": model_count,
            "supplier_names": "; ".join(sorted(fd["supplier_names"])),
        })

    out_rows.sort(key=lambda r: (-r["model_count"], -r["campaign_count"], r["part_family"]))

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "part_family", "component_name_대표", "part_numbers", "campaigns",
            "models", "campaign_count", "model_count", "supplier_names",
        ])
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"[ok] {len(out_rows)}개 공유 부품 계열 -> {OUT_CSV}")
    print(f"[verify] 전체 {len(rows)}행 중 part_number 공백 {n_blank}행, 토큰 추출 실패 {n_no_token_found}행 (합계 제외 {n_blank + n_no_token_found}행, {100*(n_blank+n_no_token_found)/len(rows):.1f}%)")
    print(f"[verify] 한 셀에서 서로 다른 family가 2개 이상 검출된 행: {n_multi_family_rows}건 (그런 경우 해당 행은 각 family 그룹에 모두 포함시켰음)")

    print("\n[preview] 상위 5개 계열:")
    for r in out_rows[:5]:
        print(f"  {r['part_family']} | {r['component_name_대표']} | campaigns={r['campaign_count']} models={r['model_count']} | {r['models']}")

    row_940c3 = next((r for r in out_rows if r["part_family"] == "940C3"), None)
    if row_940c3:
        ok = row_940c3["model_count"] >= 2
        print(f"\n[verify] 940C3(클러스터) 계열 존재: True, model_count={row_940c3['model_count']} (>=2: {ok})")
        print(f"  campaigns: {row_940c3['campaigns']}")
        print(f"  models: {row_940c3['models']}")
    else:
        print("\n[verify] 940C3(클러스터) 계열이 shared_parts.csv에 없음 — 확인 필요")

    return out_rows


if __name__ == "__main__":
    build()
