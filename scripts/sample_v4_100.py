#!/usr/bin/env python3
"""
sample_v4_100.py — v4 검증용 100건 샘플링

hk_electrical_recent_full.csv(16,964행, 51개 원본 컬럼)에서 100건 추출:
- 검증용 50건: v4의 두 핵심 메커니즘이 실제로 작동하는지 보기 위한 의도적 추출
  A) 다중 CMPLID 앵커링(예시1·2·3형): 2행 이상인 ODINO를 골라 그 ODINO의 행 전부 포함
  B) UNKNOWN OR OTHER + 형제 있음(예시5형): compdesc1=UNKNOWN OR OTHER이면서 같은 ODINO에
     다른 compdesc1을 가진 행이 존재하는 행만 추출. 형제 행 자체는 표본에 없어도 됨 —
     형제 COMPDESC 조회는 항상 hk_electrical_recent_full.csv 전체를 인덱스로 쓰므로
     100건 표본 안에 형제가 같이 들어있을 필요가 없다.
  C) UNKNOWN OR OTHER + 형제 없음(예시6형): compdesc1=UNKNOWN OR OTHER이고 그 ODINO의
     유일한 행인 것만 추출
- 무작위 50건: 위 검증용 50건을 제외한 나머지에서 단순 무작위(seed 고정)

출력: 51개 원본 컬럼 그대로 + sample_group 컬럼(A_multi_cmplid/B_unknown_with_sibling/
C_unknown_no_sibling/RANDOM) 추가.
"""
import pandas as pd

SRC_PATH = "data/processed/hk_electrical_recent_full.csv"
OUT_PATH = "data/samples/sample_100_v4.csv"
SEED = 42

N_GROUP_A_ODINOS = 11  # 다중 CMPLID ODINO 개수 (그 행 전부를 포함하므로 실제 행수는 더 많음)
N_GROUP_B = 13
N_GROUP_C = 13


def main():
    df = pd.read_csv(SRC_PATH, encoding="utf-8-sig", dtype=str)
    df["compdesc1"] = df["COMPDESC"].str.split(":").str[0].str.strip()

    odino_counts = df.groupby("ODINO").size()
    multi_odinos = odino_counts[odino_counts >= 2].index

    # Group A: 다중 CMPLID ODINO 중 N_GROUP_A_ODINOS개를 골라 그 ODINO의 행 전부
    rng_odinos = pd.Series(multi_odinos).sample(n=N_GROUP_A_ODINOS, random_state=SEED)
    group_a = df[df["ODINO"].isin(rng_odinos)].copy()
    group_a["sample_group"] = "A_multi_cmplid"

    # 형제 유무 판정: compdesc1=UNKNOWN OR OTHER인 행 중, 같은 ODINO에 UNKNOWN OR OTHER가
    # 아닌 다른 compdesc1이 하나라도 있으면 "형제 있음"
    unk = df[df["compdesc1"] == "UNKNOWN OR OTHER"].copy()
    odino_has_other = df[df["compdesc1"] != "UNKNOWN OR OTHER"]["ODINO"].unique()
    unk_with_sibling = unk[unk["ODINO"].isin(odino_has_other)]
    unk_without_sibling = unk[~unk["ODINO"].isin(odino_has_other)]

    # Group A에 이미 뽑힌 ODINO는 B/C에서 제외(중복 방지)
    unk_with_sibling = unk_with_sibling[~unk_with_sibling["ODINO"].isin(rng_odinos)]
    unk_without_sibling = unk_without_sibling[~unk_without_sibling["ODINO"].isin(rng_odinos)]

    group_b = unk_with_sibling.sample(n=N_GROUP_B, random_state=SEED).copy()
    group_b["sample_group"] = "B_unknown_with_sibling"

    group_c = unk_without_sibling.sample(n=N_GROUP_C, random_state=SEED).copy()
    group_c["sample_group"] = "C_unknown_no_sibling"

    curated = pd.concat([group_a, group_b, group_c], ignore_index=True)
    print(f"검증용 그룹: A(다중CMPLID) {len(group_a)}행({N_GROUP_A_ODINOS}개 ODINO) / "
          f"B(UNKNOWN+형제있음) {len(group_b)}행 / C(UNKNOWN+형제없음) {len(group_c)}행 "
          f"= 총 {len(curated)}행")

    n_random = 100 - len(curated)
    rest = df[~df["CMPLID"].isin(curated["CMPLID"])]
    random_sample = rest.sample(n=n_random, random_state=SEED).copy()
    random_sample["sample_group"] = "RANDOM"

    out = pd.concat([curated, random_sample], ignore_index=True)
    out = out.drop(columns=["compdesc1"])  # 파생 컬럼 제거, 원본 51컬럼만 유지

    print(f"무작위 {len(random_sample)}행 추가 → 최종 {len(out)}행")
    out.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"saved -> {OUT_PATH}")

    print("\n=== 검증 ===")
    print(out["sample_group"].value_counts())
    print(f"고유 ODINO: {out['ODINO'].nunique()}건 / 총 {len(out)}행")
    print(f"고유 CMPLID: {out['CMPLID'].nunique()}건 (=행수와 같아야 함)")


if __name__ == "__main__":
    main()
