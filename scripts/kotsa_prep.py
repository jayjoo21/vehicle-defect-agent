#!/usr/bin/env python3
"""
kotsa_prep.py — 한국교통안전공단 차종별 리콜대수 전처리
① 로드·기본 검증
② 현대·기아 필터 + 차명 정규화 + 영문 모델 매핑
③ SW 관련 플래그
출력: data/processed/kotsa_recalls_hk.csv
"""
import re
import pandas as pd
from pathlib import Path

RAW = Path("data/raw/한국교통안전공단_차종별 리콜대수_20251231.csv")
OUT = Path("data/processed/kotsa_recalls_hk.csv")

# ── 한글 차명 → 영문 모델 매핑 테이블 ─────────────────
KO_TO_EN: dict[str, str] = {
    # 현대
    "투싼": "TUCSON",
    "팰리세이드": "PALISADE",
    "싼타페": "SANTA FE",
    "산타페": "SANTA FE",
    "아이오닉5": "IONIQ 5",
    "아이오닉 5": "IONIQ 5",
    "아이오닉6": "IONIQ 6",
    "아이오닉 6": "IONIQ 6",
    "아이오닉": "IONIQ",
    "쏘나타": "SONATA",
    "그랜저": "GRANDEUR",
    "아반떼": "ELANTRA",
    "코나": "KONA",
    "코나 일렉트릭": "KONA ELECTRIC",
    "코나일렉트릭": "KONA ELECTRIC",
    "넥쏘": "NEXO",
    "베뉴": "VENUE",
    "스타리아": "STARIA",
    "포터": "PORTER",
    "엑센트": "ACCENT",
    "i30": "I30",
    "i40": "I40",
    # 기아
    "스포티지": "SPORTAGE",
    "쏘렌토": "SORENTO",
    "카니발": "CARNIVAL",
    "텔루라이드": "TELLURIDE",
    "셀토스": "SELTOS",
    "니로": "NIRO",
    "니로 ev": "NIRO EV",
    "니로ev": "NIRO EV",
    "스팅어": "STINGER",
    "봉고": "BONGO",
    "레이": "RAY",
    "k3": "K3",
    "k5": "K5",
    "k7": "K7",
    "k8": "K8",
    "k9": "K9",
    "ev3": "EV3",
    "ev6": "EV6",
    "ev9": "EV9",
    "모닝": "MORNING",
    "하이": "HI",
    "쏘울": "SOUL",
    "모하비": "MOHAVE",
    "카렌스": "CARENS",
    "포르테": "FORTE",
    "맥스크루즈": "MAX CRUZ",
    "아슬란": "ASLAN",
    "제네시스": "GENESIS",
    # 제네시스 (현대 계열)
    "g70": "G70",
    "g80": "G80",
    "g90": "G90",
    "gv60": "GV60",
    "gv70": "GV70",
    "gv80": "GV80",
}

# 미국 미판매 확정 모델
KO_ONLY_MODELS = {
    "PORTER", "BONGO", "RAY", "STARIA", "K7", "K8", "K9",
    "MORNING", "I30", "I40", "HI", "GRANDEUR", "EV3",
    "MOHAVE", "CARENS", "MAX CRUZ", "ASLAN", "GENESIS",
}

SW_KEYWORDS = [
    "소프트웨어", "sw", "제어기", "전자제어", "ecm", "ecu", "전장",
    "센서", "카메라", "ota", "배터리", "충전", "bms", "인버터",
    "모터제어", "통신", "모듈", "펌웨어", "계기판", "클러스터",
    "adas", "자율", "운전보조",
]

HK_MAKERS = ["현대", "기아"]


def normalize_model_name(raw: str) -> str:
    """괄호·특수문자 제거 후 공백 정규화"""
    # 괄호 내용 제거: 투싼(NX4) → 투싼
    s = re.sub(r"[(\（][^)\）]*[)\）]", "", raw)
    # 로마자/숫자 변형 정규화: Ⅱ→2, Ⅲ→3
    s = s.replace("Ⅱ", "2").replace("Ⅲ", "3")
    # 연속 공백 정리
    s = re.sub(r"\s+", " ", s).strip()
    return s


def translate_model(normalized: str) -> tuple[str, bool]:
    """(영문 모델명, 미국판매여부). 매핑 없으면 원문 대문자 반환."""
    low = normalized.lower().strip()
    # 완전 일치
    if low in KO_TO_EN:
        en = KO_TO_EN[low]
        return en, en not in KO_ONLY_MODELS
    # 부분 일치 (긴 것 우선)
    for ko, en in sorted(KO_TO_EN.items(), key=lambda x: -len(x[0])):
        if ko in low:
            return en, en not in KO_ONLY_MODELS
    # 영문 모델명 그대로 (숫자+알파벳)
    m = re.search(r"[A-Za-z][A-Za-z0-9 \-]+", normalized)
    if m:
        en = m.group().upper().strip()
        return en, en not in KO_ONLY_MODELS
    return normalized.upper(), False


def is_sw(reason: str) -> bool:
    low = str(reason).lower()
    return any(kw in low for kw in SW_KEYWORDS)


def main():
    # ── ① 로드 ────────────────────────────────────────
    df = pd.read_csv(RAW, encoding="cp949", dtype=str)
    df.columns = [c.strip() for c in df.columns]

    print(f"=== ① 기본 검증 ===")
    print(f"전체 행 수: {len(df):,}")
    print(f"컬럼: {df.columns.tolist()}")

    # 날짜 정규화
    df["리콜개시일_dt"] = pd.to_datetime(df["리콜개시일"], errors="coerce")
    valid_dt = df["리콜개시일_dt"].notna()
    print(f"리콜개시일 범위: {df.loc[valid_dt,'리콜개시일_dt'].min().date()} ~ "
          f"{df.loc[valid_dt,'리콜개시일_dt'].max().date()}")
    print(f"리콜개시일 파싱 실패: {(~valid_dt).sum()}건")

    # 제작자 분포 (상위 15)
    print(f"\n제작자 분포 (상위 15):")
    print(df["제작자"].value_counts().head(15).to_string())

    # 리콜대수 숫자 변환
    df["리콜대수_n"] = pd.to_numeric(
        df["리콜대수"].str.replace(",", ""), errors="coerce"
    )

    # ── ② 현대·기아 필터 ──────────────────────────────
    hk_mask = df["제작자"].str.contains("|".join(HK_MAKERS), na=False)
    hk = df[hk_mask].copy()
    print(f"\n=== ② 현대·기아 필터 ===")
    print(f"현대·기아 행: {len(hk):,} / 전체 {len(df):,}")
    print(f"제작자 세부:\n{hk['제작자'].value_counts().to_string()}")

    # 차명 정규화
    hk["차명_정규화"] = hk["차명"].apply(normalize_model_name)
    hk[["모델_영문", "미국판매여부"]] = hk["차명_정규화"].apply(
        lambda x: pd.Series(translate_model(x))
    )

    # ── ③ SW 플래그 ───────────────────────────────────
    hk["sw관련"] = hk["리콜사유"].apply(is_sw)
    print(f"\n=== ③ SW 관련 비율 ===")
    print(f"SW 관련: {hk['sw관련'].sum()} / {len(hk)} ({hk['sw관련'].mean():.1%})")

    # ── 저장 ──────────────────────────────────────────
    cols = [
        "제작자", "차명", "차명_정규화", "모델_영문", "미국판매여부",
        "생산기간(부터)", "생산기간(까지)", "리콜개시일", "리콜개시일_dt",
        "리콜대수", "리콜대수_n", "sw관련", "리콜사유",
    ]
    hk[cols].to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"\n저장: {OUT} ({len(hk)}행 × {len(cols)}열)")
    print(f"리콜개시일 범위: {hk['리콜개시일_dt'].min().date()} ~ {hk['리콜개시일_dt'].max().date()}")
    print(f"미국판매 가능 모델: {hk.loc[hk['미국판매여부'],'모델_영문'].nunique()}종")
    print(f"한국 단독 모델: {hk.loc[~hk['미국판매여부'],'모델_영문'].value_counts().head(10).to_string()}")

    # 매핑 못된 차명: 사전에 없어서 원문 대문자가 그대로 들어간 경우
    # (K5→K5 처럼 입력=출력인 경우는 제외)
    dict_values = set(KO_TO_EN.values())
    unmapped = hk[~hk["모델_영문"].isin(dict_values)]["차명_정규화"].value_counts()
    if not unmapped.empty:
        print(f"\n[참고] 사전 미등록 차명 (상위 10 — 수동 검토 필요):")
        print(unmapped.head(10).to_string())


if __name__ == "__main__":
    main()
