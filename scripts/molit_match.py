#!/usr/bin/env python3
"""
molit_match.py — 국토부 리콜 × NHTSA 캠페인 매칭 → kr_us_gap.csv
입력: data/processed/molit_recalls.csv
      data/recalls/recalls_sw_candidates.csv
출력: data/processed/kr_us_gap.csv
"""
import re
import pandas as pd
from pathlib import Path

MOLIT_CSV  = Path("data/processed/molit_recalls.csv")
NHTSA_CSV  = Path("data/recalls/recalls_sw_candidates.csv")
OUT_CSV    = Path("data/processed/kr_us_gap.csv")

# ──────────────────────────────────────────────
# 한국 차종명 → 미국 판매명 매핑
# ──────────────────────────────────────────────
KO_TO_EN: dict[str, str] = {
    "투싼": "TUCSON",
    "팰리세이드": "PALISADE",
    "산타페": "SANTA FE",
    "싼타페": "SANTA FE",
    "아이오닉5": "IONIQ 5",
    "아이오닉 5": "IONIQ 5",
    "아이오닉6": "IONIQ 6",
    "아이오닉 6": "IONIQ 6",
    "아이오닉": "IONIQ",
    "쏘나타": "SONATA",
    "그랜저": "GRANDEUR",
    "아반떼": "ELANTRA",
    "코나": "KONA",
    "넥쏘": "NEXO",
    "베뉴": "VENUE",
    "스타리아": "STARIA",
    "포터": "PORTER",
    "스포티지": "SPORTAGE",
    "쏘렌토": "SORENTO",
    "카니발": "CARNIVAL",
    "텔루라이드": "TELLURIDE",
    "셀토스": "SELTOS",
    "니로": "NIRO",
    "스팅어": "STINGER",
    "봉고": "BONGO",       # 미국 미판매
    "레이": "RAY",         # 미국 미판매
    "k5": "K5",
    "k8": "K8",
    "k3": "K3",
    "ev6": "EV6",
    "ev9": "EV9",
    "ioniq": "IONIQ",
    "g80": "G80",
    "g70": "G70",
    "gv80": "GV80",
    "gv70": "GV70",
    "gv60": "GV60",
}

# 미국 미판매 모델 (한국 단독)
KO_ONLY_MODELS = {"RAY", "BONGO", "K8", "PORTER", "STARIA", "MOHAVE"}

# 제조사 표준화
MFR_MAP: dict[str, str] = {
    "현대": "HYUNDAI",
    "현대자동차": "HYUNDAI",
    "기아": "KIA",
    "기아자동차": "KIA",
    "케이지모빌리티": "KG MOBILITY",
    "쌍용": "SSANGYONG",
    "르노": "RENAULT",
    "한국지엠": "GM KOREA",
}


def normalize_make(raw) -> str:
    if not isinstance(raw, str):
        return ""
    raw = raw.strip()
    for ko, en in MFR_MAP.items():
        if ko in raw:
            return en
    return raw.upper()


def translate_model(raw: str) -> tuple[str, float]:
    """(영문 모델명, 번역 신뢰도 0~1)"""
    raw_lower = raw.lower().strip()
    # 직접 매핑 우선
    for ko, en in KO_TO_EN.items():
        if ko in raw_lower or ko in raw:
            return en, 1.0
    # 영문 포함 여부 (괄호 안 영문: "투싼(TUCSON)")
    m = re.search(r"\(([A-Z][A-Z0-9 \-]+)\)", raw)
    if m:
        return m.group(1).strip(), 0.9
    # 영문만으로 된 모델명
    m = re.match(r"^[A-Z][A-Z0-9 \-]+$", raw.upper())
    if m:
        return raw.upper().strip(), 0.8
    return raw.upper().strip(), 0.3


def match_nhtsa(make_en: str, model_en: str, press_date: str, nhtsa: pd.DataFrame) -> list[dict]:
    """해당 make/model에 대한 NHTSA 캠페인 후보 반환 (날짜 무관)"""
    if not make_en or not model_en:
        return []
    df = nhtsa[nhtsa["Make"] == make_en].copy()
    if df.empty:
        return []
    model_up = model_en.upper()
    # 부분 일치
    mask = df["Model"].str.upper().str.contains(model_up, regex=False, na=False)
    if not mask.any():
        # IONIQ → IONIQ 5, IONIQ 6 등 prefix 매칭
        mask = df["Model"].str.upper().str.startswith(model_up, na=False)
    hits = df[mask].copy()
    if hits.empty:
        return []
    results = []
    for _, row in hits.iterrows():
        us_date = row.get("report_date_iso", "")
        gap_days = None
        if press_date and us_date:
            try:
                kr_dt = pd.to_datetime(press_date)
                us_dt = pd.to_datetime(us_date)
                gap_days = (kr_dt - us_dt).days  # 양수 = 미국 선행
            except Exception:
                pass
        results.append({
            "미국_캠페인번호": row["NHTSACampaignNumber"],
            "미국_접수일": us_date,
            "미국_컴포넌트": row.get("Component", ""),
            "gap_days": gap_days,
        })
    # gap_days 절댓값 오름차순 정렬
    results.sort(key=lambda x: abs(x["gap_days"]) if x["gap_days"] is not None else 9999)
    return results


def classify_gap(gap_days: int | None, is_ko_only: bool) -> str:
    if is_ko_only:
        return "한국단독"
    if gap_days is None:
        return "매칭불가"
    if gap_days > 0:
        return "미국선행"
    if gap_days < 0:
        return "한국선행"
    return "동시"


def matching_confidence(model_conf: float, gap_days: int | None) -> str:
    if model_conf < 0.5:
        return "낮음"
    if gap_days is None:
        return "낮음"
    if model_conf >= 0.9 and abs(gap_days) <= 180:
        return "높음"
    if model_conf >= 0.7:
        return "중간"
    return "낮음"


def main():
    molit = pd.read_csv(MOLIT_CSV, encoding="utf-8-sig")
    nhtsa = pd.read_csv(NHTSA_CSV, encoding="utf-8-sig")
    print(f"molit_recalls: {len(molit)}행  |  nhtsa sw_candidates: {len(nhtsa)}행\n")

    # 현대·기아만 필터
    hk_mask = molit["제조사"].apply(normalize_make).isin(["HYUNDAI", "KIA"])
    hk = molit[hk_mask].copy()
    print(f"현대·기아 항목: {len(hk)}행 / 전체 {len(molit)}행\n")

    rows = []
    for _, r in hk.iterrows():
        make_en = normalize_make(r["제조사"])
        model_en, model_conf = translate_model(r.get("차종_원문", ""))
        press_date = r.get("발표일", "")
        is_ko_only = model_en in KO_ONLY_MODELS

        candidates = [] if is_ko_only else match_nhtsa(make_en, model_en, press_date, nhtsa)

        if candidates:
            best = candidates[0]
            rows.append({
                "한국_발표일": press_date,
                "제조사": make_en,
                "한국_차종_원문": r.get("차종_원문", ""),
                "모델_영문": model_en,
                "한국_대수": r.get("대수"),
                "한국_원인": r.get("원인", ""),
                "한국_증상": r.get("증상", ""),
                "한국_시정시작일": r.get("시정시작일", ""),
                "sw관련_한국": r.get("sw관련", False),
                "미국_캠페인번호": best["미국_캠페인번호"],
                "미국_접수일": best["미국_접수일"],
                "미국_컴포넌트": best["미국_컴포넌트"],
                "시차_일": best["gap_days"],
                "분류": classify_gap(best["gap_days"], is_ko_only),
                "매칭확신도": matching_confidence(model_conf, best["gap_days"]),
                "후보수": len(candidates),
            })
        else:
            rows.append({
                "한국_발표일": press_date,
                "제조사": make_en,
                "한국_차종_원문": r.get("차종_원문", ""),
                "모델_영문": model_en,
                "한국_대수": r.get("대수"),
                "한국_원인": r.get("원인", ""),
                "한국_증상": r.get("증상", ""),
                "한국_시정시작일": r.get("시정시작일", ""),
                "sw관련_한국": r.get("sw관련", False),
                "미국_캠페인번호": "",
                "미국_접수일": "",
                "미국_컴포넌트": "",
                "시차_일": None,
                "분류": classify_gap(None, is_ko_only),
                "매칭확신도": "낮음",
                "후보수": 0,
            })

    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    print(f"✓ kr_us_gap.csv: {len(out)}행 × {len(out.columns)}열")
    print(f"\n[분류 분포]")
    print(out["분류"].value_counts().to_string())
    print(f"\n[확신도 분포]")
    print(out["매칭확신도"].value_counts().to_string())

    # ── 검증: 투싼 26V400000 (+8일) ──────────────
    tucson_rows = out[
        out["모델_영문"].str.upper().str.contains("TUCSON", na=False) &
        out["한국_발표일"].str.contains("2026-07-02", na=False)
    ]
    if not tucson_rows.empty:
        t = tucson_rows.iloc[0]
        print(f"\n[검증] 투싼 2026-07-02 행: 캠페인={t['미국_캠페인번호']}, "
              f"미국접수일={t['미국_접수일']}, 시차={t['시차_일']}일, 분류={t['분류']}")
        exp_ok = (t["미국_캠페인번호"] == "26V400000" and t["시차_일"] == 8)
        print(f"  ✓ 기대값(26V400000, +8일) 일치!" if exp_ok else
              f"  ⚠ 기대값과 다름 (26V400000, +8일 기대)")
    else:
        print("\n⚠  투싼 2026-07-02 검증 행을 찾지 못했습니다.")

    # ── 검증: 레이 → 한국단독 ──────────────────
    ray_rows = out[out["모델_영문"].str.upper().str.contains("RAY", na=False)]
    if not ray_rows.empty:
        ray_cls = ray_rows.iloc[0]["분류"]
        print(f"[검증] 레이 분류={ray_cls} {'✓' if ray_cls == '한국단독' else '⚠ (한국단독 기대)'}")

    # ── 시차 표 출력 ──────────────────────────
    matched = out[out["미국_캠페인번호"] != ""].copy()
    if not matched.empty:
        print(f"\n[시차 표 — 매칭 성공 {len(matched)}건]")
        display_cols = ["한국_발표일", "제조사", "모델_영문", "미국_캠페인번호",
                        "미국_접수일", "시차_일", "분류", "매칭확신도"]
        print(matched[display_cols].sort_values("시차_일").to_string(index=False))


if __name__ == "__main__":
    main()
