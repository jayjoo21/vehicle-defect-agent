"""
INV-01: 조사 루프용 안전 쿼리 템플릿 함수 모음

설계 원칙
---------
1. LLM은 이 함수들의 '이름'만 보고 어떤 걸 호출할지 고른다 (자유 코드 생성 X).
2. 모든 함수는 원본 CSV(1.6만 건)를 pandas로 집계만 한다. LLM은 절대 숫자를 계산하지 않는다.
3. 결과는 항상 dict(JSON 직렬화 가능)로 반환 -> LLM에게 그대로 보여줄 수 있음.
4. 0건일 때는 예외를 던지지 않고 '건수 0'을 명시한 dict를 돌려준다.
   -> 조사 루프에서 "조건 완화 후 1회 재시도" 로직이 이 신호를 보고 판단.

컬럼명 가정 (원본 CSV 실제 확인 후 CONFIG만 수정하면 됨)
---------------------------------------------------
odino, cmplid, model, model_year, dateComplaintFiled, part_category(조인 후 생성),
symptoms(조인 후 생성), severity(조인 후 생성), make(조인 후 생성)

2026-07-20 수정 이력 (v4 전환 + 버그 수정)
------------------------------------------
1. join 키를 odino 단독 -> cmplid로 변경.
   원인: v4 STR 산출물(str01_sample100_v4_results.jsonl)은 처리 단위가
   ODINO가 아니라 CMPLID(같은 신고 안에서도 결함 유형별로 행이 나뉨)라서,
   odino 기준 merge는 형제 CMPLID가 있는 신고에서 many-to-many가 되어
   행 수가 부풀어 통계가 조용히 오염되는 버그가 있었다(실측으로 확인).
   cmplid는 원본·구조화 결과 양쪽에서 유일하므로 1:1 매칭이 보장된다.
2. part_category 별칭 컬럼 추가.
   v4 STR 산출물은 part_category 필드가 없고 compdesc1(대분류)/compdesc2
   (중분류)로 나뉘어 있다(compdesc1은 LLM 출력이 아니라 코드가 원본
   COMPDESC를 그대로 파싱한 결정론적 필드). 아래 쿼리 함수들이 기존
   part_category 인자명을 그대로 쓸 수 있도록 df["part_category"] =
   df["compdesc1"] 별칭을 추가했다 — 함수 시그니처는 안 바꿔도 됨.
   실제 값은 v3(언더스코어 8종, INSTRUMENT_CLUSTER 등)이 아니라 NHTSA
   원본 그대로(공백 표기) 7종: ELECTRICAL SYSTEM / UNKNOWN OR OTHER /
   FORWARD COLLISION AVOIDANCE / VEHICLE SPEED CONTROL / LANE DEPARTURE /
   BACK OVER PREVENTION / ELECTRONIC STABILITY CONTROL (ESC).
3. make(제조사) 필터 추가.
   기존엔 모든 쿼리 함수가 part_category/symptom만 받아서, "기아"/"현대"로
   좁혀 물어도 실제로는 두 제조사를 합친 전체 분포가 나오는 문제가 있었다
   (cht01_chat_pipeline.py가 화면에 "KIA 기준"이라고 표시만 하고 실제
   필터링은 안 하는 게 실행 로그로 확인됨). 원본 CSV의 MAKETXT 컬럼을
   enriched df에 make로 조인해 추가하고, 모든 get_* 함수에 make: str | None
   = None 선택적 파라미터를 추가했다. 기본값 None이라 기존 호출부
   (자동 감시 파이프라인 등 make를 안 넘기는 코드)는 수정 없이 그대로
   동작한다(하위 호환) — make를 넘기면 그 값으로 추가 필터링될 뿐이다.
"""

import pandas as pd
from pathlib import Path

# ------------------------------------------------------------------
# 0. 설정 & 데이터 로드/조인
# ------------------------------------------------------------------

RAW_CSV_PATH = "data/processed/hk_electrical_recent_full.csv"  # 1.6만 건 원본
STRUCT_JSONL_PATH = "data/processed/str01_sample100_v4_results.jsonl"
STRUCT_JSONL_FALLBACKS = (
    "data/processed/llm_struct_test_results.jsonl",
    "llm_struct_test_results.jsonl",
    "str01_sample100_v4_results.jsonl",
)

INSUFFICIENT_SYMPTOM = "정보 부족으로 판단 불가"
INSUFFICIENT_EVIDENCE = "(정보 부족으로 근거 문장 없음)"

COLUMN_MAP = {
    "cmplid": "CMPLID",
    "id": "ODINO",
    "model": "MODELTXT",
    "model_year": "YEARTXT",
    "date": "FAILDATE",
    "make": "MAKETXT",
}

LEGACY_PART_CATEGORY_MAP = {
    "ELECTRICAL_SYSTEM": "ELECTRICAL SYSTEM",
    "INSTRUMENT_CLUSTER": "ELECTRICAL SYSTEM",
    "PROPULSION_BATTERY": "ELECTRICAL SYSTEM",
    "POWERTRAIN_SW": "ELECTRICAL SYSTEM",
    "NON_ELECTRICAL": "UNKNOWN OR OTHER",
    "INSUFFICIENT_INFO": "UNKNOWN OR OTHER",
}


def _resolve_struct_path(path: str) -> str:
    requested = Path(path)
    if requested.exists():
        return str(requested)
    if path == STRUCT_JSONL_PATH:
        for fallback in STRUCT_JSONL_FALLBACKS:
            if Path(fallback).exists():
                return fallback
    raise FileNotFoundError(f"STR 구조화 JSONL을 찾을 수 없습니다: {path}")


def _parse_date_series(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip()
    compact = text.str.fullmatch(r"\d{8}", na=False)
    parsed = pd.to_datetime(text.where(compact), format="%Y%m%d", errors="coerce")
    return parsed.fillna(pd.to_datetime(text.where(~compact), errors="coerce"))


def _is_blank(value) -> bool:
    return value is None or pd.isna(value) or not str(value).strip()


def _has_usable_symptom(value) -> bool:
    return isinstance(value, list) and any(
        str(item).strip() and str(item).strip() != INSUFFICIENT_SYMPTOM
        for item in value
    )


def _insufficient_mask(df: pd.DataFrame) -> pd.Series:
    if "insufficient_info" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["insufficient_info"].map(
        lambda value: value is True or str(value).strip().lower() in {"1", "true", "yes", "y"}
    )


def load_enriched_df(raw_csv_path: str = RAW_CSV_PATH,
                      struct_jsonl_path: str = STRUCT_JSONL_PATH) -> pd.DataFrame:
    """
    상진님의 v4 구조화 결과(cmplid 기준)와 원본 CSV(model/model_year/make 포함)를
    cmplid 키로 조인해서, 쿼리 함수들이 공통으로 쓸 '보강된' 데이터프레임을 만든다.

    이 함수는 조사 루프 시작 시 1회만 호출해서 캐싱해두고,
    아래 get_* 함수들은 이 df를 인자로 받아 재사용하는 걸 권장한다.
    (매 쿼리마다 파일을 다시 읽지 않도록)
    """
    raw = pd.read_csv(raw_csv_path, dtype=str, low_memory=False, encoding="utf-8-sig")
    struct = pd.read_json(_resolve_struct_path(struct_jsonl_path), lines=True)

    raw = raw.rename(columns={
        COLUMN_MAP["cmplid"]: "cmplid",
        COLUMN_MAP["id"]: "odino",
        COLUMN_MAP["model"]: "model",
        COLUMN_MAP["model_year"]: "model_year",
        COLUMN_MAP["date"]: "date_filed",
        COLUMN_MAP["make"]: "make",
    })

    raw_required = {"cmplid", "odino", "model", "model_year", "date_filed", "make"}
    missing_raw = raw_required - set(raw.columns)
    if missing_raw:
        raise ValueError(f"원본 CSV 필수 컬럼 누락: {sorted(missing_raw)}")
    if "odino" not in struct.columns:
        raise ValueError("STR JSONL 필수 컬럼 누락: odino")

    is_v4 = "cmplid" in struct.columns or "compdesc1" in struct.columns
    if is_v4:
        required_v4 = {
            "cmplid", "odino", "compdesc1", "compdesc2", "symptoms",
            "severity", "driving_context", "evidence_quote", "insufficient_info",
        }
        missing_v4 = required_v4 - set(struct.columns)
        if missing_v4:
            raise ValueError(f"STR v4 필수 필드 누락: {sorted(missing_v4)}")
        for column in ("cmplid", "compdesc1", "compdesc2"):
            if struct[column].map(_is_blank).any():
                raise ValueError(f"STR v4 {column}에 빈 값이 있습니다.")

    if "symptoms" not in struct.columns or not struct["symptoms"].map(
        lambda value: isinstance(value, list) and len(value) > 0
    ).all():
        raise ValueError("STR symptoms는 비어 있지 않은 배열이어야 합니다.")
    if "evidence_quote" not in struct.columns or struct["evidence_quote"].map(_is_blank).any():
        raise ValueError("STR evidence_quote에 빈 값이 있습니다.")

    for frame in (raw, struct):
        frame["odino"] = frame["odino"].astype("string").str.strip()

    use_cmplid = "cmplid" in struct.columns
    if use_cmplid:
        raw["cmplid"] = raw["cmplid"].astype("string").str.strip()
        struct["cmplid"] = struct["cmplid"].astype("string").str.strip()
        join_key = "cmplid"
    else:
        struct["cmplid"] = struct["odino"]
        join_key = "odino"

    if "compdesc1" not in struct.columns:
        if "part_category" not in struct.columns:
            raise ValueError("STR JSONL에 compdesc1 또는 part_category가 필요합니다.")
        legacy = struct["part_category"].astype("string").str.strip().str.upper()
        struct["compdesc1"] = legacy.map(LEGACY_PART_CATEGORY_MAP).fillna(legacy)
    if "compdesc2" not in struct.columns:
        struct["compdesc2"] = "no"

    meta = raw[[join_key, "model", "model_year", "date_filed", "make"]].drop_duplicates(join_key)
    df = struct.merge(meta, on=join_key, how="left", validate="many_to_one")
    if len(df) != len(struct):
        raise ValueError(f"merge 후 행 수 불일치: struct={len(struct)}, merged={len(df)}")
    unmatched = int(df["model"].isna().sum())
    if unmatched:
        raise ValueError(f"STR {unmatched}행이 원본 CSV와 {join_key}로 매칭되지 않았습니다.")

    df["date_filed"] = _parse_date_series(df["date_filed"])
    df["part_category"] = df["compdesc1"]

    # make 값 표준화(대문자) — MAKE_ALIASES 등 호출부가 "KIA"/"HYUNDAI"처럼
    # 대문자로 넘기는 관례와 맞춘다.
    df["make"] = df["make"].astype(str).str.strip().str.upper()

    return df


def _filter_base(
    df: pd.DataFrame,
    part_category: str | list[str] | None = None,
    symptom: str | None = None,
    make: str | None = None,
    model: str | None = None,
    model_year: str | int | None = None,
) -> pd.DataFrame:
    """공통 필터. 카테고리는 단일 값과 OR 목록을 모두 지원한다."""
    out = df.copy()
    out = out[~_insufficient_mask(out)]
    if "symptoms" in out.columns:
        out = out[out["symptoms"].map(_has_usable_symptom)]
    if part_category:
        if isinstance(part_category, (list, tuple, set)):
            out = out[out["part_category"].isin(list(part_category))]
        else:
            out = out[out["part_category"] == part_category]
    if symptom:
        # symptoms는 리스트이므로 부분 포함 여부로 필터
        out = out[out["symptoms"].apply(
            lambda lst: any(symptom in s for s in lst) if isinstance(lst, list) else False
        )]
    if make:
        out = out[out["make"] == str(make).strip().upper()]
    if model:
        out = out[
            out["model"].astype(str).str.strip().str.upper()
            == str(model).strip().upper()
        ]
    if model_year is not None and str(model_year).strip():
        expected_year = str(model_year).strip().removesuffix(".0")
        years = out["model_year"].astype(str).str.strip().str.removesuffix(".0")
        out = out[years == expected_year]
    return out


# ------------------------------------------------------------------
# 1. 증상 분포 — 조사 루프의 사실상 1번 타자
# ------------------------------------------------------------------

def get_symptom_distribution(
    df: pd.DataFrame,
    part_category: str | list[str],
    symptom: str | None = None,
    make: str | None = None,
    model: str | None = None,
    model_year: str | int | None = None,
) -> dict:
    """선택 조건 안에서 증상별 신고 건수를 집계한다."""
    sub = _filter_base(
        df,
        part_category=part_category,
        symptom=symptom,
        make=make,
        model=model,
        model_year=model_year,
    )
    if len(sub) == 0:
        return {"status": "no_data", "count": 0, "part_category": part_category, "make": make}

    exploded = sub.explode("symptoms")
    counts = exploded["symptoms"].value_counts().to_dict()
    return {
        "status": "ok",
        "part_category": part_category,
        "make": make,
        "total_reports": len(sub),
        "symptom_counts": counts,
    }


def get_symptom_distribution_by_model(
    df: pd.DataFrame,
    part_category: str | list[str],
    model: str,
    model_year: str | int | None = None,
    make: str | None = None,
    symptom: str | None = None,
) -> dict:
    """특정 차종(+연식)으로 좁혀서, 그 안에서 어떤 증상이 몇 건인지.

    get_symptom_distribution은 part_category 전체를 보기 때문에, 카테고리 안에
    여러 차종이 섞여 있으면 "이 증상이 이 차종만의 문제인지 카테고리 전체의
    흔한 증상인지" 구분이 안 된다. 질문에 이미 특정 차종(+연식)이 명시된 경우
    (예: "EV9 2024 계기판 증상") 이 함수로 좁혀서 봐야 정확하다.
    2026-07-20: make 추가(선택). 모델명이 제조사 간 겹치지 않으면 보통
    불필요하지만, 방어적으로 같이 좁힐 수 있게 둠.
    """
    sub = _filter_base(
        df,
        part_category=part_category,
        symptom=symptom,
        make=make,
        model=model,
        model_year=model_year,
    )
    if len(sub) == 0:
        return {"status": "no_data", "count": 0, "part_category": part_category, "model": model,
                "model_year": model_year, "make": make}

    exploded = sub.explode("symptoms")
    counts = exploded["symptoms"].value_counts().to_dict()
    return {
        "status": "ok",
        "part_category": part_category,
        "model": model,
        "model_year": model_year,
        "make": make,
        "total_reports": len(sub),
        "symptom_counts": counts,
    }


# ------------------------------------------------------------------
# 2. 차종×연식 교차표 — "2025년식 투싼 집중" 같은 조합 가설 검증의 핵심
#    (단독 get_year_distribution / get_model_distribution만으로는
#     차종과 연식의 '조합'을 검증할 수 없어서 이 함수가 필수)
# ------------------------------------------------------------------

def get_model_year_breakdown(
    df: pd.DataFrame,
    part_category: str | list[str],
    symptom: str | None = None,
    make: str | None = None,
    model: str | None = None,
    model_year: str | int | None = None,
) -> dict:
    """
    차종×연식을 동시에 교차 집계.
    반환 예: {"투싼": {"2025": 33, "2024": 5}, "싼타페": {"2025": 2}}
    -> "2025년식 투싼이 83% 집중" 같은 조합 가설을 이 함수 하나로 검증 가능.
    2026-07-20: make 추가(선택).
    """
    sub = _filter_base(
        df,
        part_category=part_category,
        symptom=symptom,
        make=make,
        model=model,
        model_year=model_year,
    )
    if len(sub) == 0:
        return {"status": "no_data", "count": 0}

    cross = sub.groupby(["model", "model_year"]).size().reset_index(name="count")
    if len(cross) == 0:
        return {"status": "no_data", "count": 0, "note": "model/model_year 조인 실패로 그룹 없음"}
    total = len(sub)

    breakdown = {}
    for _, row in cross.iterrows():
        model = str(row["model"])
        year = str(int(row["model_year"])) if pd.notna(row["model_year"]) else "unknown"
        breakdown.setdefault(model, {})[year] = int(row["count"])

    # LLM이 바로 판단할 수 있게 최다 조합의 비율도 같이 계산해서 준다
    top_combo = cross.sort_values("count", ascending=False).iloc[0]
    top_share = round(top_combo["count"] / total * 100, 1)

    return {
        "status": "ok",
        "total_reports": total,
        "breakdown": breakdown,
        "top_combo": {
            "model": str(top_combo["model"]),
            "model_year": str(int(top_combo["model_year"])) if pd.notna(top_combo["model_year"]) else "unknown",
            "count": int(top_combo["count"]),
            "share_pct": top_share,
        },
    }


# 참고: 단독 분포가 필요한 경우를 위해 개별 함수도 남겨두되,
# LLM 프롬프트/도구 설명에는 "조합 가설엔 get_model_year_breakdown을 써라"라고 명시할 것.

def get_year_distribution(
    df: pd.DataFrame,
    part_category: str | list[str],
    symptom: str | None = None,
    make: str | None = None,
    model: str | None = None,
    model_year: str | int | None = None,
) -> dict:
    """연식별 분포만 (차종 무관). 계절/연식 자체 트렌드 확인용.
    2026-07-20: make 추가(선택)."""
    sub = _filter_base(
        df,
        part_category=part_category,
        symptom=symptom,
        make=make,
        model=model,
        model_year=model_year,
    )
    if len(sub) == 0:
        return {"status": "no_data", "count": 0}
    counts = sub["model_year"].value_counts().sort_index().to_dict()
    counts = {str(int(k)) if pd.notna(k) else "unknown": int(v) for k, v in counts.items()}
    return {"status": "ok", "total_reports": len(sub), "year_counts": counts}


def get_model_distribution(
    df: pd.DataFrame,
    part_category: str | list[str],
    symptom: str | None = None,
    make: str | None = None,
    model: str | None = None,
    model_year: str | int | None = None,
) -> dict:
    """차종별 분포만 (연식 무관). 특정 차종 고유 문제인지 확인용.
    2026-07-20: make 추가(선택)."""
    sub = _filter_base(
        df,
        part_category=part_category,
        symptom=symptom,
        make=make,
        model=model,
        model_year=model_year,
    )
    if len(sub) == 0:
        return {"status": "no_data", "count": 0}
    counts = sub["model"].value_counts().to_dict()
    return {"status": "ok", "total_reports": len(sub), "model_counts": counts}


# ------------------------------------------------------------------
# 3. 월별 추이 — 계절성 vs 진짜 급증 구분
# ------------------------------------------------------------------

def get_monthly_trend(
    df: pd.DataFrame,
    part_category: str | list[str],
    symptom: str | None = None,
    months: int = 12,
    make: str | None = None,
    model: str | None = None,
    model_year: str | int | None = None,
) -> dict:
    """2026-07-20: make 추가(선택)."""
    sub = _filter_base(
        df,
        part_category=part_category,
        symptom=symptom,
        make=make,
        model=model,
        model_year=model_year,
    )
    if len(sub) == 0:
        return {"status": "no_data", "count": 0}

    cutoff = sub["date_filed"].max() - pd.DateOffset(months=months)
    sub = sub[sub["date_filed"] >= cutoff]
    if len(sub) == 0:
        return {"status": "no_data", "count": 0}

    monthly = sub.groupby(sub["date_filed"].dt.to_period("M")).size()
    monthly_dict = {str(k): int(v) for k, v in monthly.items()}
    return {"status": "ok", "total_reports": len(sub), "monthly_counts": monthly_dict}


# ------------------------------------------------------------------
# 4. 심각도 분포
# ------------------------------------------------------------------

def get_severity_breakdown(
    df: pd.DataFrame,
    part_category: str | list[str],
    symptom: str | None = None,
    make: str | None = None,
    model: str | None = None,
    model_year: str | int | None = None,
) -> dict:
    """2026-07-20: make 추가(선택)."""
    sub = _filter_base(
        df,
        part_category=part_category,
        symptom=symptom,
        make=make,
        model=model,
        model_year=model_year,
    )
    if len(sub) == 0:
        return {"status": "no_data", "count": 0}
    counts = sub["severity"].value_counts().to_dict()
    return {"status": "ok", "total_reports": len(sub), "severity_counts": counts}


# ------------------------------------------------------------------
# 5. 리콜 이력 대조 (정답지 CSV와 조인 — 별도 파일)
# ------------------------------------------------------------------

def check_recall_match(model: str, model_year: str,
                        recalls_df: pd.DataFrame) -> dict:
    """
    data/recalls/recalls_hk_campaigns.csv 등 정답지와 대조.
    이미 리콜된 조합인지 확인 -> mentions_existing_recall 필드 검증에도 쓸 수 있음.
    """
    matches = recalls_df[
        (recalls_df["model"] == model) & (recalls_df["model_year"].astype(str) == str(model_year))
    ]
    if len(matches) == 0:
        return {"status": "no_match", "already_recalled": False}
    return {
        "status": "ok",
        "already_recalled": True,
        "recall_count": len(matches),
        "recall_dates": matches["recall_date"].astype(str).tolist() if "recall_date" in matches else [],
    }


# ------------------------------------------------------------------
# 6. 한·미 리콜 시차
# ------------------------------------------------------------------

def get_us_kr_gap(model: str, us_recalls_df: pd.DataFrame,
                   kr_recalls_df: pd.DataFrame) -> dict:
    us = us_recalls_df[us_recalls_df["model"] == model]
    kr = kr_recalls_df[kr_recalls_df["model"] == model]

    if len(us) == 0:
        return {"status": "no_us_recall"}
    if len(kr) == 0:
        return {"status": "us_recalled_kr_not_yet", "us_recall_date": str(us.iloc[0]["recall_date"])}

    us_date = pd.to_datetime(us.iloc[0]["recall_date"])
    kr_date = pd.to_datetime(kr.iloc[0]["recall_date"])
    gap_days = (kr_date - us_date).days

    return {
        "status": "ok",
        "us_recall_date": str(us_date.date()),
        "kr_recall_date": str(kr_date.date()),
        "gap_days": gap_days,
    }


# ------------------------------------------------------------------
# 도구 레지스트리 — LLM에게 "고를 수 있는 함수 목록"으로 그대로 전달
# ------------------------------------------------------------------

TOOL_REGISTRY = {
    "get_symptom_distribution": {
        "func": get_symptom_distribution,
        "when_to_use": "부품 카테고리 안에서 대표 증상이 뭔지 먼저 파악할 때 (조사 루프 1순위)",
    },
    "get_symptom_distribution_by_model": {
        "func": get_symptom_distribution_by_model,
        "when_to_use": "질문에 이미 특정 차종(+연식)이 명시됐을 때, 그 차종 안에서만 증상 분포를 볼 때 "
                       "(get_symptom_distribution은 카테고리 전체를 보므로, 여러 차종이 섞인 카테고리에서 "
                       "특정 차종 질문이 들어오면 이걸 우선 사용해서 그 차종만의 증상인지 확인할 것)",
    },
    "get_model_year_breakdown": {
        "func": get_model_year_breakdown,
        "when_to_use": "'특정 연식의 특정 차종'처럼 두 조건이 결합된 가설을 검증할 때 (필수 - 단독 분포로는 조합 검증 불가)",
    },
    "get_year_distribution": {
        "func": get_year_distribution,
        "when_to_use": "차종 무관하게 연식 자체의 트렌드만 볼 때",
    },
    "get_model_distribution": {
        "func": get_model_distribution,
        "when_to_use": "연식 무관하게 특정 차종 고유 문제인지 볼 때",
    },
    "get_monthly_trend": {
        "func": get_monthly_trend,
        "when_to_use": "계절성(냉난방 등)과 진짜 급증을 구분할 때",
    },
    "get_severity_breakdown": {
        "func": get_severity_breakdown,
        "when_to_use": "위험도 분포를 확인해 우선순위를 매길 때",
    },
    "check_recall_match": {
        "func": check_recall_match,
        "when_to_use": "이미 리콜된 적 있는 조합인지 확인할 때",
    },
    "get_us_kr_gap": {
        "func": get_us_kr_gap,
        "when_to_use": "한·미 리콜 시차(국내 미조치 여부)를 확인할 때",
    },
}
