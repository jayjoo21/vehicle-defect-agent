#!/usr/bin/env python3
"""
kotsa_gap_v2.py
④ kr_us_gap_v2.csv 생성 (보도자료 기반 + KOTSA 기반, date_basis 구분)
⑤ NHTSA SW 후보 캠페인 × KOTSA 한국 리콜 대응 여부 확인
"""
import pandas as pd
from pathlib import Path

KOTSA    = Path("data/processed/kotsa_recalls_hk.csv")
NHTSA    = Path("data/recalls/recalls_sw_candidates.csv")
GAP_V1   = Path("data/processed/kr_us_gap.csv")
OUT_V2   = Path("data/processed/kr_us_gap_v2.csv")
CAMP_OUT = Path("data/processed/campaign_kotsa_check.csv")

# Korean string constants as unicode escapes to avoid write-time encoding issues
KO_US_FIRST   = "한국선행"     # 한국선행
KO_MOLIT      = "보도자료"     # 보도자료
KO_KOTSA_BASE = "KOTSA리콜개시일"  # KOTSA리콜개시일
KO_SYMPTOM    = "한국_증상"   # 한국_증상
KO_SW_KR      = "sw관련_한국"  # sw관련_한국
KO_SW_COL     = "분류"                  # 분류
KO_SW_EN      = "한국_SW관련"  # 한국_SW관련
KO_MATCH_YN   = "한국_대응여부"   # 한국_대응여부
KO_FOCUS_COL  = "주목캐페인"   # 주목캠페인
KO_CAMP_NO    = "캐페인번호"   # 캠페인번호
KO_HUSI       = "후보"                     # 후보

MAKE_MAP = {"현대자동차": "HYUNDAI",   # 현대자동차
            "기아": "KIA"}                           # 기아

FOCUS_CAMPAIGNS = {
    "23V531000", "24V204000", "24V757000",
    "25V006000", "25V115000",
}


def normalize_make(raw: str) -> str:
    for ko, en in MAKE_MAP.items():
        if ko in str(raw):
            return en
    return str(raw).upper()


def model_match(nhtsa_model: str, kotsa_model: str) -> bool:
    n = nhtsa_model.upper().strip()
    k = kotsa_model.upper().strip()
    if not n or not k:
        return False
    return n in k or k in n or k.split()[0] in n


def find_kotsa_matches(make_en: str, model_en: str, nhtsa_date: str,
                       kotsa_df: pd.DataFrame,
                       window_days: int = 730) -> pd.DataFrame:
    sub = kotsa_df[kotsa_df["make_en"] == make_en].copy()
    if sub.empty:
        return sub
    mask = sub["모델_영문"].apply(lambda x: model_match(model_en, str(x)))
    sub = sub[mask].copy()
    if sub.empty or not nhtsa_date:
        return sub
    try:
        ndt = pd.to_datetime(nhtsa_date)
        sub = sub[
            (sub["리콜개시일_dt"] - ndt).abs() <= pd.Timedelta(days=window_days)
        ].copy()
        sub["gap_days"] = (sub["리콜개시일_dt"] - ndt).dt.days
    except Exception:
        pass
    return sub


def classify_gap(gap) -> str:
    if gap is None or (isinstance(gap, float) and pd.isna(gap)):
        return "매칭불가"   # 매칭불가
    gap = float(gap)
    if gap > 0:
        return "미국선행"   # 미국선행
    if gap < 0:
        return KO_US_FIRST                  # 한국선행
    return "동시"                   # 동시


def main():
    kotsa = pd.read_csv(KOTSA, encoding="utf-8-sig")
    kotsa["리콜개시일_dt"] = pd.to_datetime(
        kotsa["리콜개시일_dt"], errors="coerce"
    )
    kotsa["make_en"] = kotsa["제작자"].apply(normalize_make)

    nhtsa = pd.read_csv(NHTSA, encoding="utf-8-sig")
    nhtsa_camps = (
        nhtsa[["NHTSACampaignNumber", "Make", "Model", "report_date_iso",
               "Component", "Summary"]]
        .drop_duplicates("NHTSACampaignNumber")
        .copy()
    )

    # ④-A: 기존 kr_us_gap (보도자료 기반)
    gap_v1 = pd.read_csv(GAP_V1, encoding="utf-8-sig")
    gap_v1["date_basis"] = KO_MOLIT

    # ④-B: KOTSA SW 관련 행 우선 매칭
    sw_kotsa = kotsa[kotsa["sw관련"]].copy()   # sw관련
    print(f"KOTSA SW 관련 행: {len(sw_kotsa)} / {len(kotsa)}")

    kotsa_rows = []
    for _, camp in nhtsa_camps.iterrows():
        make_en   = camp["Make"]
        if make_en not in ("HYUNDAI", "KIA"):
            continue
        model_en  = camp["Model"]
        nhtsa_date= camp["report_date_iso"]
        camp_no   = camp["NHTSACampaignNumber"]

        matches = find_kotsa_matches(make_en, model_en, nhtsa_date, sw_kotsa)
        if matches.empty:
            matches = find_kotsa_matches(make_en, model_en, nhtsa_date, kotsa)

        if not matches.empty:
            if "gap_days" in matches.columns:
                best = matches.loc[matches["gap_days"].abs().idxmin()]
            else:
                best = matches.iloc[0]
            gap_days = best.get("gap_days", None)
            kotsa_rows.append({
                "date_basis"       : KO_KOTSA_BASE,
                "한국_발표일": str(best["리콜개시일"])[:10],
                "제조사": make_en,
                "한국_차종_원문": best.get("차명", ""),
                "모델_영문": model_en,
                "한국_대수": best.get("리콜대수_n"),
                "한국_원인": str(best.get("리콜사유", ""))[:100],
                KO_SYMPTOM         : "",
                "한국_시정시작일": str(best["리콜개시일"])[:10],
                KO_SW_KR           : bool(best.get("sw관련", False)),
                "미국_캠페인번호": camp_no,
                "미국_접수일": nhtsa_date,
                "미국_컴포넌트": camp.get("Component", ""),
                "시차_일": float(gap_days) if gap_days is not None else None,
                KO_SW_COL          : classify_gap(gap_days),
                "매칭확신도": "중간",
                "후보수": len(matches),
            })
        else:
            kotsa_rows.append({
                "date_basis"       : KO_KOTSA_BASE,
                "한국_발표일": "",
                "제조사": make_en,
                "한국_차종_원문": "",
                "모델_영문": model_en,
                "한국_대수": None,
                "한국_원인": "",
                KO_SYMPTOM         : "",
                "한국_시정시작일": "",
                KO_SW_KR           : False,
                "미국_캠페인번호": camp_no,
                "미국_접수일": nhtsa_date,
                "미국_컴포넌트": camp.get("Component", ""),
                "시차_일": None,
                KO_SW_COL          : "매칭불가",
                "매칭확신도": "낙음",
                "후보수": 0,
            })

    df_kotsa = pd.DataFrame(kotsa_rows)

    # ④-C: 합치기 (공통 컬럼 기준)
    shared_cols = ["date_basis"] + [c for c in df_kotsa.columns if c in gap_v1.columns and c != "date_basis"]
    for c in shared_cols:
        if c not in gap_v1.columns:
            gap_v1[c] = ""
        if c not in df_kotsa.columns:
            df_kotsa[c] = ""

    gap_v2 = pd.concat([gap_v1[shared_cols], df_kotsa[shared_cols]], ignore_index=True)
    gap_v2.to_csv(OUT_V2, index=False, encoding="utf-8-sig")

    print(f"\n[OK] kr_us_gap_v2.csv: {len(gap_v2)}행")
    molit_n = (gap_v2["date_basis"] == KO_MOLIT).sum()
    kotsa_n = (gap_v2["date_basis"] == KO_KOTSA_BASE).sum()
    print(f"  보도자료 기반: {molit_n}건")
    print(f"  KOTSA 기반  : {kotsa_n}건")
    if KO_SW_COL in df_kotsa.columns:
        print("\n[KOTSA 기반 분류 분포]")
        print(df_kotsa[KO_SW_COL].value_counts().to_string())

    # ⑤ 캠페인 x KOTSA 대응 여부
    print("\n" + "=" * 60)
    print(f"⑤ NHTSA SW {KO_HUSI} 캠페인 x KOTSA 한국 리콜 대응 여부")
    print("=" * 60)

    camp_rows = []
    for _, camp in nhtsa_camps.sort_values("report_date_iso").iterrows():
        make_en   = camp["Make"]
        if make_en not in ("HYUNDAI", "KIA"):
            continue
        model_en  = camp["Model"]
        nhtsa_date= camp["report_date_iso"]
        camp_no   = camp["NHTSACampaignNumber"]
        component = str(camp.get("Component", ""))

        matches = find_kotsa_matches(make_en, model_en, nhtsa_date, kotsa)
        if matches.empty:
            matched = False
            best_gap = None
            kotsa_date_str = ""
            kotsa_model_str = ""
            kotsa_sw = False
        else:
            if "gap_days" in matches.columns:
                best = matches.loc[matches["gap_days"].abs().idxmin()]
            else:
                best = matches.iloc[0]
            matched = True
            best_gap = best.get("gap_days")
            kotsa_date_str = str(best["리콜개시일"])[:10]
            kotsa_model_str = str(best.get("차명", ""))
            kotsa_sw = bool(best.get("sw관련", False))

        is_focus = camp_no in FOCUS_CAMPAIGNS
        camp_rows.append({
            KO_CAMP_NO       : camp_no,
            "제조사": make_en,
            "NHTSA모델": model_en,
            "NHTSA접수일": nhtsa_date,
            "NHTSA컴포넌트": component[:60],
            KO_MATCH_YN      : "O" if matched else "X",
            "한국_리콜개시일": kotsa_date_str,
            "한국_차명": kotsa_model_str,
            KO_SW_EN         : "O" if kotsa_sw else "",
            "시차_일": best_gap,
            KO_SW_COL        : classify_gap(best_gap),
            KO_FOCUS_COL     : "[*]" if is_focus else "",
        })

        flag  = "[*]" if is_focus else "   "
        mstr  = f"O ({kotsa_date_str}, gap={best_gap:.0f}d)" if matched else "X"
        print(f"  {flag} {camp_no} | {make_en:<7} | {model_en:<14} | {nhtsa_date} | KR={mstr}")

    df_camp = pd.DataFrame(camp_rows)
    df_camp.to_csv(CAMP_OUT, index=False, encoding="utf-8-sig")

    matched_n = df_camp[KO_MATCH_YN].eq("O").sum()
    total_n   = len(df_camp)
    print(f"\n전체 HK {total_n}건 중 한국 대응 있음: {matched_n}건 ({matched_n/total_n:.0%})")

    focus_df = df_camp[df_camp[KO_FOCUS_COL] == "[*]"]
    print("\n[주목 캠페인 상세]")
    for _, r in focus_df.iterrows():
        print(f"  {r[KO_CAMP_NO]} | {r['NHTSA모델']:<14} | {r['NHTSA접수일']} | "
              f"KR={r[KO_MATCH_YN]} | 개시={r[chr(0xD55C)+chr(0xAD6D)+chr(0x5F)+chr(0xB9AC)+chr(0xCF5C)+chr(0xAC1C)+chr(0xC2DC)+chr(0xC77C)]} | "
              f"gap={r[chr(0xC2DC)+chr(0xCC28)+chr(0x5F)+chr(0xC77C)]} | SW={r[KO_SW_EN]}")

    print(f"\n[OK] 캠페인 대응표 저장: {CAMP_OUT} ({total_n}건)")


if __name__ == "__main__":
    main()
