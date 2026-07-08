#허정윤: INV-01  

"""
MOBISCOPE INV-01 — 안전한 CSV 조회 템플릿
============================================================
목적
- data/processed/hk_electrical_recent_full.csv 를 대상으로 AI가 직접 코드를 만들지 않고
  미리 정의된 함수만 호출해 통계를 조회하게 한다.
- 조사 루프(INV-02/03), 채팅 파이프라인(CHT-01), 대시보드가 같은 조회 함수를 공유한다.

설계 원칙
- VIN 등 민감/식별 컬럼은 로드 단계에서 제거한다.
- COMPDESC == "UNKNOWN OR OTHER"는 절대 일괄 배제하지 않는다.
- LLM은 계산하지 않는다. 필터링·집계·급증 계산은 pandas 함수가 수행한다.
- 반환값은 DataFrame 또는 dict로 고정해 대시보드 연동이 쉽도록 한다.
- 모든 결과는 "미검증 소비자 신고 데이터" 기준이며 결함 확정 표현을 만들지 않는다.

대표 조회 함수 8종
1) q_year_distribution          연식 분포
2) q_monthly_trend              월별 접수 추이
3) q_component_distribution     부품 라벨 분포
4) q_model_ranking              차종/연식 상위 분포
5) q_safety_flag_summary        화재·충돌·부상·사망 플래그 요약
6) q_component_by_year          특정 부품/파트 카테고리 × 연식
7) q_recent_surge               최근 N개월 vs 직전 N개월 급증 탐지
8) q_text_evidence_samples      원문 근거 샘플 조회(Citation 후보)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import re

import pandas as pd


# GitHub 기준 기본 경로. 샌드박스/로컬 테스트를 위해 fallback도 둔다.
DEFAULT_CSV_PATH = Path("data/processed/hk_electrical_recent_full.csv")
FALLBACK_CSV_PATHS = [
    Path("/mnt/data/hk_electrical_recent_full.csv"),
    Path("hk_electrical_recent_full.csv"),
]

DATE_COLUMNS = ["FAILDATE", "LDATE", "DATEA"]
DROP_COLUMNS = ["VIN"]
REQUIRED_COLUMNS = {
    "ODINO", "CMPLID", "MAKETXT", "MODELTXT", "YEARTXT", "FAILDATE", "LDATE",
    "COMPDESC", "CDESCR", "CRASH", "FIRE", "INJURED", "DEATHS",
}

# 구조화 결과 part_category -> CSV/원문 검색 키워드 매핑.
# UNKNOWN OR OTHER를 배제하지 않기 위해 키워드는 필터 도구로만 사용한다.
PART_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "ELECTRICAL_SYSTEM": [
        "ELECTRICAL", "BATTERY", "ALTERNATOR", "WIRING", "INSTRUMENT", "CLUSTER",
        "DASH", "DISPLAY", "WARNING", "LIGHT", "12V", "ICCU",
    ],
    "ADAS": [
        "LANE", "DEPARTURE", "ASSIST", "FORWARD COLLISION", "AEB", "ADAS",
        "BLIND", "CAMERA", "RADAR", "SENSOR", "ELECTRONIC STABILITY",
    ],
    "POWERTRAIN_SW": [
        "ENGINE", "POWER TRAIN", "THROTTLE", "ECM", "ECU", "STALL", "SHUT", "LOSS OF POWER",
    ],
    "NON_ELECTRICAL": ["SUSPENSION", "STRUCTURE", "AIR BAG", "SEAT", "TIRES", "WHEELS"],
    "INSUFFICIENT_INFO": [],
}

SAFETY_TEXT_KEYWORDS = [
    "fire", "smoke", "burn", "stall", "stalled", "shut off", "loss of power", "lost power",
    "brake", "braking", "steer", "steering", "accelerat", "crash", "collision",
    "warning light", "dashboard", "cluster", "instrument", "speedometer", "while driving",
]

SEVERITY_ORDER = {"CRITICAL": 4, "SERIOUS": 3, "MODERATE": 2, "MINOR": 1, "UNKNOWN": 0}


@dataclass(frozen=True)
class LoadReport:
    rows: int
    columns: int
    faildate_min: str | None
    faildate_max: str | None
    ldate_min: str | None
    ldate_max: str | None
    dropped_columns: list[str]
    missing_required_columns: list[str]


def _resolve_path(path: str | Path | None, fallbacks: Iterable[Path]) -> Path:
    """기본 경로가 없을 때 샌드박스/로컬 fallback 경로를 찾는다."""
    if path is not None:
        p = Path(path)
        if p.exists():
            return p
        # 사용자가 기본값을 넘겼는데 GitHub data/processed가 아직 없을 수 있으므로 fallback 허용.
        if str(p) != str(DEFAULT_CSV_PATH):
            raise FileNotFoundError(f"CSV 파일을 찾을 수 없습니다: {p}")

    if DEFAULT_CSV_PATH.exists():
        return DEFAULT_CSV_PATH
    for fb in fallbacks:
        if fb.exists():
            return fb
    raise FileNotFoundError(
        "CSV 파일을 찾을 수 없습니다. 기본 위치: data/processed/hk_electrical_recent_full.csv"
    )


def _parse_yyyymmdd(series: pd.Series) -> pd.Series:
    """YYYYMMDD 문자열을 datetime으로 변환한다. 이미 datetime이면 그대로 정규화한다."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce")
    s = series.astype("string").str.strip()
    return pd.to_datetime(s, format="%Y%m%d", errors="coerce")


def _normalize_yn(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.upper().fillna("N")


def _safe_numeric(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series(dtype="float64")
    return pd.to_numeric(series, errors="coerce")


def make_load_report(df: pd.DataFrame, dropped: list[str]) -> LoadReport:
    def dt_minmax(col: str) -> tuple[str | None, str | None]:
        if col not in df.columns or df[col].dropna().empty:
            return None, None
        return df[col].min().strftime("%Y-%m-%d"), df[col].max().strftime("%Y-%m-%d")

    fmin, fmax = dt_minmax("FAILDATE")
    lmin, lmax = dt_minmax("LDATE")
    return LoadReport(
        rows=len(df),
        columns=len(df.columns),
        faildate_min=fmin,
        faildate_max=fmax,
        ldate_min=lmin,
        ldate_max=lmax,
        dropped_columns=dropped,
        missing_required_columns=sorted(REQUIRED_COLUMNS - set(df.columns)),
    )


def load_processed(path: str | Path | None = None, *, verbose: bool = True) -> pd.DataFrame:
    """
    처리된 CSV를 로드하고 조사에 필요한 타입을 정리한다.

    반환 DataFrame 속성
    - df.attrs["load_report"]에 LoadReport dict 저장
    - df.attrs["source_path"]에 실제 로드 경로 저장
    """
    csv_path = _resolve_path(path, FALLBACK_CSV_PATHS)
    df = pd.read_csv(csv_path, dtype=str, low_memory=False, encoding="utf-8-sig")
    df.columns = [str(c).strip().upper() for c in df.columns]

    dropped: list[str] = []
    for col in DROP_COLUMNS:
        if col in df.columns:
            df = df.drop(columns=[col])
            dropped.append(col)

    for col in DATE_COLUMNS:
        if col in df.columns:
            df[col] = _parse_yyyymmdd(df[col])

    for col in ["MAKETXT", "MODELTXT", "COMPDESC", "STATE", "CITY"]:
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip()

    if "YEARTXT" in df.columns:
        df["YEARTXT"] = df["YEARTXT"].astype("string").str.strip()
        df["YEAR_INT"] = pd.to_numeric(df["YEARTXT"], errors="coerce").astype("Int64")

    for col in ["CRASH", "FIRE"]:
        if col in df.columns:
            df[col] = _normalize_yn(df[col])

    for col in ["INJURED", "DEATHS", "MILES"]:
        if col in df.columns:
            df[f"{col}_NUM"] = pd.to_numeric(df[col], errors="coerce")

    report = make_load_report(df, dropped)
    df.attrs["load_report"] = report.__dict__
    df.attrs["source_path"] = str(csv_path)

    if verbose:
        print(
            f"[INV-01 LOAD] rows={report.rows:,} cols={report.columns} "
            f"FAILDATE={report.faildate_min}~{report.faildate_max} "
            f"LDATE={report.ldate_min}~{report.ldate_max} dropped={dropped}"
        )
        if report.missing_required_columns:
            print(f"[INV-01 WARN] missing columns: {report.missing_required_columns}")
    return df


def _contains_any_text(series: pd.Series, keywords: list[str]) -> pd.Series:
    if not keywords:
        return pd.Series(False, index=series.index)
    escaped = [re.escape(k) for k in keywords if str(k).strip()]
    if not escaped:
        return pd.Series(False, index=series.index)
    pattern = "|".join(escaped)
    return series.fillna("").astype("string").str.contains(pattern, case=False, regex=True, na=False)


def keywords_for_part(part_category: str | None, component_keyword: str | None = None) -> list[str]:
    """part_category와 직접 키워드를 합쳐 중복 제거한 검색 키워드를 만든다."""
    keys: list[str] = []
    if part_category:
        keys.extend(PART_CATEGORY_KEYWORDS.get(str(part_category).upper(), []))
    if component_keyword:
        keys.append(str(component_keyword))
    # 순서 보존 dedupe
    seen: set[str] = set()
    out: list[str] = []
    for k in keys:
        kk = str(k).strip()
        if kk and kk.upper() not in seen:
            seen.add(kk.upper())
            out.append(kk)
    return out


def filter_records(
    df: pd.DataFrame,
    *,
    make: str | None = None,
    model: str | None = None,
    year: int | str | None = None,
    part_category: str | None = None,
    component_keyword: str | None = None,
    text_keywords: list[str] | None = None,
    date_col: str = "LDATE",
    date_from: str | pd.Timestamp | None = None,
    date_to: str | pd.Timestamp | None = None,
    months_back: int | None = None,
) -> pd.DataFrame:
    """
    공통 필터 함수. 모든 조회 템플릿이 이 함수만 사용한다.

    주의: UNKNOWN OR OTHER는 기본적으로 배제하지 않는다. part/component 필터가 있는 경우에도
    COMPDESC 또는 CDESCR 중 하나에 키워드가 등장하면 포함한다.
    """
    sub = df.copy()

    if make and "MAKETXT" in sub.columns:
        sub = sub[sub["MAKETXT"].str.upper() == str(make).strip().upper()]
    if model and "MODELTXT" in sub.columns:
        sub = sub[sub["MODELTXT"].str.upper() == str(model).strip().upper()]
    if year is not None and "YEARTXT" in sub.columns:
        sub = sub[sub["YEARTXT"].astype("string") == str(year).strip()]

    part_keys = keywords_for_part(part_category, component_keyword)
    if part_keys:
        comp_mask = _contains_any_text(sub.get("COMPDESC", pd.Series("", index=sub.index)), part_keys)
        text_mask = _contains_any_text(sub.get("CDESCR", pd.Series("", index=sub.index)), part_keys)
        sub = sub[comp_mask | text_mask]

    if text_keywords:
        text_mask = _contains_any_text(sub.get("CDESCR", pd.Series("", index=sub.index)), text_keywords)
        sub = sub[text_mask]

    if date_col in sub.columns:
        if months_back is not None and len(sub) > 0:
            max_date = sub[date_col].max()
            if pd.notna(max_date):
                date_from = max_date - pd.DateOffset(months=months_back)
        if date_from is not None:
            sub = sub[sub[date_col] >= pd.to_datetime(date_from, errors="coerce")]
        if date_to is not None:
            sub = sub[sub[date_col] <= pd.to_datetime(date_to, errors="coerce")]

    return sub.copy()


def _add_pct(out: pd.DataFrame, count_col: str = "count") -> pd.DataFrame:
    total = out[count_col].sum()
    out["pct"] = (out[count_col] / total * 100).round(2) if total else 0.0
    return out


def q_year_distribution(df: pd.DataFrame, **filters: Any) -> pd.DataFrame:
    """연식별 불만 건수. 반환: year, count, pct"""
    sub = filter_records(df, **filters)
    if sub.empty or "YEARTXT" not in sub.columns:
        return pd.DataFrame(columns=["year", "count", "pct"])
    out = (
        sub["YEARTXT"].fillna("UNKNOWN")
        .value_counts(dropna=False)
        .rename_axis("year")
        .reset_index(name="count")
        .sort_values("year")
        .reset_index(drop=True)
    )
    return _add_pct(out)


def q_monthly_trend(df: pd.DataFrame, date_col: str = "LDATE", **filters: Any) -> pd.DataFrame:
    """월별 접수/발생 추이. 반환: ym, count"""
    sub = filter_records(df, date_col=date_col, **filters)
    if sub.empty or date_col not in sub.columns:
        return pd.DataFrame(columns=["ym", "count"])
    s = sub[date_col].dropna()
    if s.empty:
        return pd.DataFrame(columns=["ym", "count"])
    out = (
        s.dt.to_period("M")
        .value_counts()
        .rename_axis("ym")
        .reset_index(name="count")
        .sort_values("ym")
        .reset_index(drop=True)
    )
    out["ym"] = out["ym"].astype(str)
    return out


def q_component_distribution(df: pd.DataFrame, top_n: int = 20, **filters: Any) -> pd.DataFrame:
    """COMPDESC 부품 라벨 상위 분포. UNKNOWN OR OTHER 포함."""
    sub = filter_records(df, **filters)
    if sub.empty or "COMPDESC" not in sub.columns:
        return pd.DataFrame(columns=["component", "count", "pct"])
    out = (
        sub["COMPDESC"].fillna("(빈값)")
        .value_counts(dropna=False)
        .head(top_n)
        .rename_axis("component")
        .reset_index(name="count")
    )
    out["pct"] = (out["count"] / len(sub) * 100).round(2) if len(sub) else 0.0
    return out


def q_model_ranking(df: pd.DataFrame, top_n: int = 15, **filters: Any) -> pd.DataFrame:
    """제조사+모델+연식 조합별 상위 불만 건수."""
    sub = filter_records(df, **filters)
    group_cols = [c for c in ["MAKETXT", "MODELTXT", "YEARTXT"] if c in sub.columns]
    if sub.empty or not group_cols:
        return pd.DataFrame(columns=["make", "model", "year", "count", "pct"])
    out = (
        sub.groupby(group_cols, dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )
    out = out.rename(columns={"MAKETXT": "make", "MODELTXT": "model", "YEARTXT": "year"})
    out["pct"] = (out["count"] / len(sub) * 100).round(2)
    return out


def q_safety_flag_summary(df: pd.DataFrame, **filters: Any) -> dict[str, Any]:
    """화재·충돌·부상·사망 플래그와 주행안전 키워드 포함 건수 요약."""
    sub = filter_records(df, **filters)
    n = len(sub)

    fire = int((sub.get("FIRE", pd.Series(dtype="string")) == "Y").sum()) if "FIRE" in sub else 0
    crash = int((sub.get("CRASH", pd.Series(dtype="string")) == "Y").sum()) if "CRASH" in sub else 0
    injured = int((_safe_numeric(sub.get("INJURED_NUM", sub.get("INJURED"))).fillna(0) > 0).sum()) if n else 0
    deaths = int((_safe_numeric(sub.get("DEATHS_NUM", sub.get("DEATHS"))).fillna(0) > 0).sum()) if n else 0
    safety_text = int(_contains_any_text(sub.get("CDESCR", pd.Series("", index=sub.index)), SAFETY_TEXT_KEYWORDS).sum()) if n else 0

    def pct(x: int) -> float:
        return round(x / n * 100, 2) if n else 0.0

    return {
        "total_count": n,
        "fire_count": fire,
        "fire_pct": pct(fire),
        "crash_count": crash,
        "crash_pct": pct(crash),
        "injured_count": injured,
        "injured_pct": pct(injured),
        "deaths_count": deaths,
        "deaths_pct": pct(deaths),
        "safety_text_count": safety_text,
        "safety_text_pct": pct(safety_text),
        "note": "미검증 소비자 신고의 플래그/서술 기준 요약입니다. 결함 확정이 아닙니다.",
    }


def q_component_by_year(
    df: pd.DataFrame,
    component_keyword: str | None = None,
    *,
    part_category: str | None = None,
    **filters: Any,
) -> pd.DataFrame:
    """특정 component_keyword 또는 part_category에 해당하는 행의 연식별 건수."""
    sub = filter_records(df, component_keyword=component_keyword, part_category=part_category, **filters)
    if sub.empty or "YEARTXT" not in sub.columns:
        return pd.DataFrame(columns=["year", "count", "pct"])
    out = (
        sub["YEARTXT"].fillna("UNKNOWN")
        .value_counts(dropna=False)
        .rename_axis("year")
        .reset_index(name="count")
        .sort_values("year")
        .reset_index(drop=True)
    )
    return _add_pct(out)


def q_recent_surge(
    df: pd.DataFrame,
    *,
    months: int = 6,
    baseline_months: int | None = None,
    date_col: str = "LDATE",
    **filters: Any,
) -> dict[str, Any]:
    """
    최근 N개월과 직전 N개월을 비교해 급증 신호를 요약한다.

    반환 dict는 대시보드 카드로 바로 쓰기 쉽게 설계했다.
    - recent_count, baseline_count, ratio, delta, surge_level, monthly
    """
    baseline_months = baseline_months or months
    sub = filter_records(df, date_col=date_col, **filters)
    monthly = q_monthly_trend(sub, date_col=date_col)
    if monthly.empty:
        return {
            "status": "NO_DATA",
            "recent_count": 0,
            "baseline_count": 0,
            "ratio": None,
            "delta": 0,
            "surge_level": "NO_DATA",
            "monthly": [],
        }

    monthly["ym_dt"] = pd.to_datetime(monthly["ym"] + "-01", errors="coerce")
    monthly = monthly.sort_values("ym_dt").reset_index(drop=True)
    last_month = monthly["ym_dt"].max()
    recent_start = last_month - pd.DateOffset(months=months - 1)
    baseline_end = recent_start - pd.DateOffset(days=1)
    baseline_start = baseline_end - pd.DateOffset(months=baseline_months - 1)

    recent_count = int(monthly.loc[monthly["ym_dt"].between(recent_start, last_month), "count"].sum())
    baseline_count = int(monthly.loc[monthly["ym_dt"].between(baseline_start, baseline_end), "count"].sum())
    ratio = round(recent_count / baseline_count, 2) if baseline_count > 0 else (None if recent_count == 0 else float("inf"))
    delta = recent_count - baseline_count

    if recent_count == 0:
        level = "NO_RECENT_SIGNAL"
    elif baseline_count == 0 and recent_count >= 3:
        level = "NEW_OR_RARE_SPIKE"
    elif ratio is not None and ratio >= 3 and recent_count >= 5:
        level = "STRONG_SURGE"
    elif ratio is not None and ratio >= 2 and recent_count >= 3:
        level = "WATCH"
    else:
        level = "STABLE_OR_WEAK"

    return {
        "status": "OK",
        "date_col": date_col,
        "recent_window": f"{recent_start.strftime('%Y-%m')}~{last_month.strftime('%Y-%m')}",
        "baseline_window": f"{baseline_start.strftime('%Y-%m')}~{baseline_end.strftime('%Y-%m')}",
        "recent_count": recent_count,
        "baseline_count": baseline_count,
        "ratio": ratio,
        "delta": delta,
        "surge_level": level,
        "monthly": monthly.drop(columns=["ym_dt"]).tail(months + baseline_months).to_dict("records"),
        "note": "최근 구간은 데이터 내 최대 LDATE 기준입니다. 결함 확정이 아니라 조사 우선순위 신호입니다.",
    }


def _snippet(text: str, keywords: list[str], width: int = 260) -> str:
    if not isinstance(text, str):
        return ""
    clean = " ".join(text.split())
    if not keywords:
        return clean[:width]
    lower = clean.lower()
    hit_positions = [lower.find(k.lower()) for k in keywords if k and lower.find(k.lower()) >= 0]
    pos = min(hit_positions) if hit_positions else 0
    start = max(0, pos - 80)
    end = min(len(clean), start + width)
    return clean[start:end]


def q_text_evidence_samples(
    df: pd.DataFrame,
    *,
    text_keywords: list[str] | None = None,
    part_category: str | None = None,
    component_keyword: str | None = None,
    limit: int = 10,
    **filters: Any,
) -> pd.DataFrame:
    """
    원문 CDESCR에서 근거 후보를 추출한다.
    반환 컬럼은 Citation/리포트에 필요한 최소 정보만 포함하며 VIN은 포함하지 않는다.
    """
    keys = list(text_keywords or [])
    keys.extend(keywords_for_part(part_category, component_keyword))
    keys = [k for i, k in enumerate(keys) if k and k.lower() not in {x.lower() for x in keys[:i]}]

    sub = filter_records(
        df,
        part_category=part_category,
        component_keyword=component_keyword,
        text_keywords=text_keywords,
        **filters,
    )
    if sub.empty:
        return pd.DataFrame(columns=[
            "odino", "cmplid", "make", "model", "year", "fail_date", "ldate",
            "component", "fire", "crash", "injured", "deaths", "evidence_snippet",
        ])

    # 위험 플래그/최신순 우선.
    tmp = sub.copy()
    tmp["_risk"] = 0
    if "FIRE" in tmp.columns:
        tmp["_risk"] += (tmp["FIRE"] == "Y").astype(int) * 3
    if "CRASH" in tmp.columns:
        tmp["_risk"] += (tmp["CRASH"] == "Y").astype(int) * 2
    if "INJURED_NUM" in tmp.columns:
        tmp["_risk"] += (tmp["INJURED_NUM"].fillna(0) > 0).astype(int) * 2
    if "DEATHS_NUM" in tmp.columns:
        tmp["_risk"] += (tmp["DEATHS_NUM"].fillna(0) > 0).astype(int) * 4
    if "LDATE" in tmp.columns:
        tmp = tmp.sort_values(["_risk", "LDATE"], ascending=[False, False])
    else:
        tmp = tmp.sort_values("_risk", ascending=False)
    if "ODINO" in tmp.columns:
        tmp = tmp.drop_duplicates(subset="ODINO", keep="first")

    cols = {
        "ODINO": "odino",
        "CMPLID": "cmplid",
        "MAKETXT": "make",
        "MODELTXT": "model",
        "YEARTXT": "year",
        "FAILDATE": "fail_date",
        "LDATE": "ldate",
        "COMPDESC": "component",
        "FIRE": "fire",
        "CRASH": "crash",
        "INJURED": "injured",
        "DEATHS": "deaths",
        "CDESCR": "complaint_text",
    }
    out = tmp[[c for c in cols if c in tmp.columns]].head(limit).rename(columns=cols).copy()
    for date_col in ["fail_date", "ldate"]:
        if date_col in out.columns:
            out[date_col] = pd.to_datetime(out[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    if "complaint_text" in out.columns:
        out["evidence_snippet"] = out["complaint_text"].apply(lambda x: _snippet(x, keys))
        out = out.drop(columns=["complaint_text"])
    return out.reset_index(drop=True)


def q_vehicle_component_summary(
    df: pd.DataFrame,
    *,
    make: str | None = None,
    model: str | None = None,
    year: int | str | None = None,
    part_category: str | None = None,
    component_keyword: str | None = None,
    text_keywords: list[str] | None = None,
) -> dict[str, Any]:
    """조사 루프용 종합 요약. 8대 템플릿 외 helper이지만 대시보드 카드에도 사용 가능하다."""
    base = filter_records(df, make=make, model=model, year=year)
    comp = filter_records(base, part_category=part_category, component_keyword=component_keyword)
    text = filter_records(comp, text_keywords=text_keywords) if text_keywords else comp
    year_dist = q_year_distribution(comp)
    component_dist = q_component_distribution(base, top_n=8)
    flags = q_safety_flag_summary(text)
    surge = q_recent_surge(text if len(text) else comp, months=6)
    samples = q_text_evidence_samples(
        base,
        text_keywords=text_keywords,
        part_category=part_category,
        component_keyword=component_keyword,
        limit=5,
    )
    return {
        "scope": {"make": make, "model": model, "year": str(year) if year is not None else None},
        "base_count": int(len(base)),
        "component_count": int(len(comp)),
        "text_match_count": int(len(text)),
        "year_distribution": year_dist.to_dict("records"),
        "top_components_in_scope": component_dist.to_dict("records"),
        "safety_flags": flags,
        "recent_surge": surge,
        "evidence_samples": samples.to_dict("records"),
        "note": "미검증 소비자 신고 데이터 기반 통계이며 결함 확정이 아닙니다.",
    }


QUERY_TEMPLATES = {
    "year_distribution": q_year_distribution,
    "monthly_trend": q_monthly_trend,
    "component_distribution": q_component_distribution,
    "model_ranking": q_model_ranking,
    "safety_flag_summary": q_safety_flag_summary,
    "component_by_year": q_component_by_year,
    "recent_surge": q_recent_surge,
    "text_evidence_samples": q_text_evidence_samples,
}


def run_query_template(name: str, df: pd.DataFrame, params: dict[str, Any] | None = None) -> Any:
    """LLM/채팅 파이프라인이 호출할 안전한 단일 진입점."""
    if name not in QUERY_TEMPLATES:
        raise ValueError(f"허용되지 않은 쿼리 템플릿입니다: {name}")
    return QUERY_TEMPLATES[name](df, **(params or {}))


# 기존 팀 코드와의 호환 alias
q1_year_dist = q_year_distribution
q2_monthly_trend = q_monthly_trend
q3_comp_dist = q_component_distribution
q4_top_models = q_model_ranking
q5_severity_flags = q_safety_flag_summary
q6_comp_by_year = q_component_by_year
q7_recent_surge = q_recent_surge


if __name__ == "__main__":
    df0 = load_processed()
    print("\n[CHECK] Q1 year_distribution")
    print(q_year_distribution(df0).tail().to_string(index=False))
    print("\n[CHECK] Q5 safety_flag_summary")
    print(q_safety_flag_summary(df0))
    print("\n[CHECK] Q7 recent_surge")
    print(q_recent_surge(df0, months=3))
