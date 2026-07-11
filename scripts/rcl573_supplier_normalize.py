"""
rcl573_components.csv의 supplier_name 표기 변형을 정규화하기 위한 초안 생성.
원본 CSV는 수정하지 않는다 — 정규화 적용은 사용자가 alias 파일을 확정한 뒤 별도 작업.

두 종류를 엄격히 구분한다:
1) 대소문자·법인접미어(Co./Ltd./Inc./Corp./Company 등)·공백 차이"만" 있는 변형
   → 같은 mechanical key로 묶어 confidence=auto, canonical_name 자동 제안.
   (예: "Hyundai Mobis"/"Hyundai MOBIS"/"HYUNDAI MOBIS" → 전부 대소문자 차이만.)
2) 그 외 — 핵심 키워드는 겹치지만 그 외 단어가 다른 경우(예: "Mobis Parts America",
   "Mando Pyeongtaek Plant", "Seoyon E-Hwa Alabama" vs "...AUBURN")
   → 병합하지 않고 각 행을 별도로 유지, confidence=review. 회사 동일성 판단은
   사용자가 수동으로 확정한다 — 자동 병합 절대 금지.
   1)에서 이미 병합된 그룹이라도, 그 그룹의 키워드가 다른 별도 그룹과 겹치면
   confidence는 review로 남긴다(canonical_name 제안 자체는 유지) — 그룹 내부 병합은
   안전하지만, 그 결과가 다른 그룹과 같은 회사인지는 여전히 사람이 볼 문제이기 때문.
"""
import csv
import re
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENTS_CSV = REPO_ROOT / "data" / "processed" / "rcl573_components.csv"
DISTINCT_OUT = REPO_ROOT / "data" / "processed" / "supplier_distinct.csv"
ALIAS_OUT = REPO_ROOT / "data" / "processed" / "supplier_alias_draft.csv"

LEGAL_SUFFIX_TOKENS = {
    "CO", "LTD", "LIMITED", "INC", "CORP", "CORPORATION", "LLC", "SA", "COMPANY",
}

# mechanical key 병합에서는 위 법인접미어만 벗겨내고, 그 외 단어는 절대 지우지 않는다.
# 아래는 "유사해 보이는 이름" 클러스터를 잡기 위한 별도 필터(퍼지 키워드용) —
# 모회사명·일반 지역/업종 단어를 걸러내야 "Mobis"/"Mando" 같은 실제 브랜드
# 키워드만 남는다. 이 블랙리스트는 병합에는 전혀 관여하지 않고 review 메모용.
FUZZY_STOPWORDS = LEGAL_SUFFIX_TOKENS | {
    "HYUNDAI", "KIA", "MOTOR", "MOTORS", "GROUP", "AUTOMOTIVE", "TECHNOLOGIES",
    "TECHNOLOGY", "SYSTEMS", "SYSTEM", "MANUFACTURING", "INDUSTRIES",
    "INTERNATIONAL", "PARTS", "ELECTRIFIED", "PLANT", "ENERGY", "SOLUTIONS",
    "KOREA", "OPERATIONS", "N", "NORTH", "SOUTH", "AMERICA", "POWERTRAIN",
    "POWERTRA",
}


def tokenize(name: str) -> list[str]:
    return [t for t in re.split(r"[^A-Za-z0-9]+", name.upper()) if t]


def mechanical_key(name: str) -> str:
    tokens = tokenize(name)
    while tokens and tokens[-1] in LEGAL_SUFFIX_TOKENS:
        tokens.pop()
    return " ".join(tokens)


def significant_tokens(key: str) -> set[str]:
    return {t for t in key.split() if t not in FUZZY_STOPWORDS and len(t) > 2}


def load_supplier_rows() -> list[dict]:
    with open(COMPONENTS_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return rows


def build_distinct(rows: list[dict]):
    counts: dict[str, int] = defaultdict(int)
    first_campaign: dict[str, str] = {}
    for r in rows:
        name = r["supplier_name"].strip()
        if not name:
            continue
        counts[name] += 1
        if name not in first_campaign:
            first_campaign[name] = r["campaign"]

    out_rows = sorted(counts.keys(), key=lambda n: n.upper())
    with open(DISTINCT_OUT, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["supplier_name", "count", "example_campaign"])
        for name in out_rows:
            writer.writerow([name, counts[name], first_campaign[name]])
    print(f"[ok] {len(out_rows)}개 고유 공급사명 -> {DISTINCT_OUT}")
    return counts


def choose_canonical(members: list[str], counts: dict[str, int]) -> str:
    return sorted(members, key=lambda n: (-counts[n], -len(n), n))[0]


def build_alias_draft(counts: dict[str, int]):
    names = list(counts.keys())

    # 1) mechanical key로 그룹화
    groups: dict[str, list[str]] = defaultdict(list)
    for name in names:
        groups[mechanical_key(name)].append(name)

    # 2) 그룹 간 퍼지 클러스터(키워드 공유) 탐지 — union-find
    group_keys = list(groups.keys())
    parent = {k: k for k in group_keys}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    token_map = {k: significant_tokens(k) for k in group_keys}
    for i in range(len(group_keys)):
        for j in range(i + 1, len(group_keys)):
            k1, k2 = group_keys[i], group_keys[j]
            if token_map[k1] and token_map[k1] & token_map[k2]:
                union(k1, k2)

    fuzzy_clusters: dict[str, list[str]] = defaultdict(list)
    for k in group_keys:
        fuzzy_clusters[find(k)].append(k)

    rows_out = []
    for key, members in groups.items():
        canonical = choose_canonical(members, counts)
        cluster_group_keys = [k for k in fuzzy_clusters[find(key)] if k != key]
        in_fuzzy_cluster = len(cluster_group_keys) > 0
        confidence = "review" if in_fuzzy_cluster else "auto"

        if in_fuzzy_cluster:
            sibling_examples = []
            for k in cluster_group_keys[:3]:
                sibling_examples.append(choose_canonical(groups[k], counts))
            note = f"키워드 유사 그룹(자동 병합 안 함) — 비교 대상: {', '.join(sibling_examples)}"
        elif len(members) > 1:
            note = "대소문자/법인접미어/공백 차이만 있는 변형 — 자동 병합"
        else:
            note = ""

        if key in ("", "NOT APPLICABLE", "TBD"):
            note = (note + " / " if note else "") + "실제 공급사명이 아닌 플레이스홀더 값으로 보임"

        for raw in sorted(members, key=lambda n: n.upper()):
            rows_out.append({
                "raw_name": raw,
                "canonical_name": canonical,
                "confidence": confidence,
                "note": note,
            })

    rows_out.sort(key=lambda r: (r["canonical_name"].upper(), r["raw_name"].upper()))

    with open(ALIAS_OUT, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["raw_name", "canonical_name", "confidence", "note"])
        writer.writeheader()
        writer.writerows(rows_out)

    n_auto = sum(1 for r in rows_out if r["confidence"] == "auto")
    n_review = sum(1 for r in rows_out if r["confidence"] == "review")
    print(f"[ok] {len(rows_out)}행 -> {ALIAS_OUT}")
    print(f"[verify] confidence 분포: auto={n_auto}({n_auto/len(rows_out):.1%}), review={n_review}({n_review/len(rows_out):.1%})")
    n_groups_merged = sum(1 for members in groups.values() if len(members) > 1)
    print(f"[verify] 2개 이상 raw_name이 하나로 합쳐진 mechanical 그룹 수: {n_groups_merged}")
    return rows_out


def main():
    rows = load_supplier_rows()
    counts = build_distinct(rows)
    build_alias_draft(counts)


if __name__ == "__main__":
    main()
