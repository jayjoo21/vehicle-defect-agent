"""
MOBISCOPE INV-02 / INV-03 — 조사 루프
============================================================
목적
- LLM 구조화 결과(JSONL)를 입력으로 받아 가설을 만들고,
  INV-01 쿼리 템플릿만 호출해 근거를 확인한다.
- AI가 자유롭게 pandas 코드를 생성하지 않도록 하고, while 루프 안에서
  [가설 수립 → 조회 → 유지/기각/보류]를 반복한다.

담당 기능
- INV-02: 가설 수립 및 쿼리 선택/실행
- INV-03: 근거 부족 시 조건 완화 1~N회 재시도, 그래도 부족하면 정지

판정 상태
- SUPPORTED: 동일 범위/완화 범위에서 최소 근거 기준을 넘음
- REJECTED: 넓힌 범위에서도 반복 패턴이 거의 없음
- INSUFFICIENT: 원 구조화 결과가 정보 부족이거나, 데이터는 있으나 결론 내릴 근거가 부족함

주의
- 결과는 "시그널 후보"이지 결함 확정이 아니다.
- 근거 원문은 ODINO + 짧은 snippet만 저장한다. VIN은 저장하지 않는다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re

import pandas as pd

from inv01_query_templates import (
    DEFAULT_CSV_PATH,
    load_processed,
    q_recent_surge,
    q_text_evidence_samples,
    q_vehicle_component_summary,
    q_component_by_year,
)

DEFAULT_JSONL_PATH = Path("data/processed/llm_struct_test_results.jsonl")
FALLBACK_JSONL_PATHS = [
    Path("/mnt/data/llm_struct_test_results.jsonl"),
    Path("/mnt/data/llm_struct_v2_18cases.jsonl"),
    Path("llm_struct_test_results.jsonl"),
    Path("llm_struct_v2_18cases.jsonl"),
]
DEFAULT_OUT_PATH = Path("data/processed/investigation_results.csv")
FALLBACK_OUT_PATH = Path("/mnt/data/investigation_results.csv")

MAX_ITER = 4
MIN_SUPPORT_COUNT = 3
MIN_EVIDENCE_SAMPLES = 2
STRONG_SURGE_RATIO = 2.0

STATUS_SUPPORTED = "SUPPORTED"
STATUS_REJECTED = "REJECTED"
STATUS_INSUFFICIENT = "INSUFFICIENT"
STATUS_PENDING = "PENDING"


KOREAN_TO_ENGLISH_KEYWORDS = {
    "화재": ["fire", "smoke", "burn", "flame"],
    "연기": ["smoke", "smoking", "burn"],
    "계기판": ["dashboard", "instrument", "cluster", "display", "screen", "speedometer"],
    "꺼짐": ["shut off", "turned off", "blank", "black", "went out"],
    "시동": ["stall", "stalled", "engine", "shut off", "start"],
    "동력": ["loss of power", "lost power", "power loss", "limp"],
    "제동": ["brake", "braking", "abs"],
    "브레이크": ["brake", "braking", "abs"],
    "조향": ["steer", "steering"],
    "차선": ["lane", "departure", "assist"],
    "가속": ["acceleration", "accelerator", "throttle"],
    "후방": ["rear", "backup", "camera"],
    "카메라": ["camera"],
    "배터리": ["battery", "12v"],
    "충전": ["charge", "charging", "battery"],
}

PART_DEFAULT_KEYWORDS = {
    "ELECTRICAL_SYSTEM": ["electrical", "battery", "dashboard", "cluster", "warning light", "display"],
    "ADAS": ["lane", "assist", "camera", "sensor", "collision", "aeb"],
    "POWERTRAIN_SW": ["engine", "stall", "loss of power", "throttle", "ecm", "ecu"],
    "NON_ELECTRICAL": [],
    "INSUFFICIENT_INFO": [],
}


def _resolve_path(path: str | Path | None, default: Path, fallbacks: list[Path]) -> Path:
    if path is not None:
        p = Path(path)
        if p.exists():
            return p
        if str(p) != str(default):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {p}")
    if default.exists():
        return default
    for fb in fallbacks:
        if fb.exists():
            return fb
    raise FileNotFoundError(f"파일을 찾을 수 없습니다. 기본 위치: {default}")


def load_jsonl(path: str | Path | None = None) -> list[dict[str, Any]]:
    jsonl_path = _resolve_path(path, DEFAULT_JSONL_PATH, FALLBACK_JSONL_PATHS)
    records: list[dict[str, Any]] = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"JSONL {jsonl_path} {line_no}행 파싱 실패: {e}") from e
    print(f"[INV-02 LOAD] structured_records={len(records)} path={jsonl_path}")
    return records


def _meta_by_odino(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if "ODINO" not in df.columns:
        return {}
    keep = [c for c in ["ODINO", "CMPLID", "MAKETXT", "MODELTXT", "YEARTXT", "FAILDATE", "LDATE", "COMPDESC", "CDESCR"] if c in df.columns]
    meta = df[keep].drop_duplicates(subset="ODINO", keep="first").copy()
    for col in ["FAILDATE", "LDATE"]:
        if col in meta.columns:
            meta[col] = pd.to_datetime(meta[col], errors="coerce").dt.strftime("%Y-%m-%d")
    return meta.set_index("ODINO").to_dict("index")


def extract_text_keywords(record: dict[str, Any], max_keywords: int = 8) -> list[str]:
    """한국어 구조화 증상 + 영어 evidence_quote에서 검색 키워드를 만든다."""
    symptoms = record.get("symptoms") or []
    if isinstance(symptoms, str):
        symptoms = [symptoms]
    joined_ko = " ".join(str(s) for s in symptoms)

    keywords: list[str] = []
    for ko, ens in KOREAN_TO_ENGLISH_KEYWORDS.items():
        if ko in joined_ko:
            keywords.extend(ens)

    quote = str(record.get("evidence_quote") or "")
    # 너무 흔한 단어 제외 후 4글자 이상 단어 일부를 보조 키워드로 사용.
    stop = {
        "that", "this", "with", "from", "when", "while", "vehicle", "dealer", "would",
        "could", "there", "have", "been", "were", "they", "because", "about", "after",
    }
    for token in re.findall(r"[A-Za-z][A-Za-z0-9\-]{3,}", quote.lower()):
        if token not in stop:
            keywords.append(token)

    part = str(record.get("part_category") or "").upper()
    keywords.extend(PART_DEFAULT_KEYWORDS.get(part, []))

    seen: set[str] = set()
    out: list[str] = []
    for k in keywords:
        kk = str(k).strip().lower()
        if kk and kk not in seen:
            seen.add(kk)
            out.append(k)
        if len(out) >= max_keywords:
            break
    return out


def build_hypothesis(record: dict[str, Any], meta_index: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """LLM 구조화 결과 1건을 조사 가설 dict로 변환한다."""
    odino = str(record.get("odino") or "").strip()
    meta = (meta_index or {}).get(odino, {})
    symptoms = record.get("symptoms") or []
    if isinstance(symptoms, str):
        symptoms = [symptoms]

    return {
        "odino": odino,
        "cmplid": meta.get("CMPLID"),
        "make": meta.get("MAKETXT"),
        "model": meta.get("MODELTXT"),
        "year": meta.get("YEARTXT"),
        "fail_date": meta.get("FAILDATE"),
        "ldate": meta.get("LDATE"),
        "source_component": meta.get("COMPDESC"),
        "part_category": record.get("part_category"),
        "severity": record.get("severity"),
        "symptoms": symptoms,
        "claim": "; ".join(str(s) for s in symptoms) if symptoms else "(증상 없음)",
        "driving_context": record.get("driving_context"),
        "evidence_quote": record.get("evidence_quote"),
        "insufficient_info": bool(record.get("insufficient_info")),
        "rule_notes": record.get("v2_rule_notes") or record.get("rule_notes"),
        "text_keywords": extract_text_keywords(record),
        "status": STATUS_PENDING,
        "iterations": 0,
        "support_count": 0,
        "evidence_sample_count": 0,
        "surge_ratio": None,
        "surge_level": None,
        "decision_reason": "",
        "trace": [],
        "evidence_samples": [],
    }


def make_query_plan(hypothesis: dict[str, Any], iteration: int) -> dict[str, Any]:
    """
    반복 횟수에 따라 점점 조건을 완화한다.
    1회차: 제조사+모델+연식+파트+원문키워드
    2회차: 제조사+모델+연식+파트
    3회차: 제조사+모델+파트+원문키워드
    4회차: 제조사+파트
    """
    h = hypothesis
    base = {
        "make": h.get("make"),
        "model": h.get("model"),
        "year": h.get("year"),
        "part_category": h.get("part_category"),
        "text_keywords": h.get("text_keywords") or [],
    }
    if iteration == 1:
        label = "exact_vehicle_year_part_text"
    elif iteration == 2:
        base["text_keywords"] = []
        label = "exact_vehicle_year_part"
    elif iteration == 3:
        base["year"] = None
        label = "vehicle_part_text_relaxed_year"
    else:
        base["model"] = None
        base["year"] = None
        base["text_keywords"] = []
        label = "make_part_relaxed_model_year_text"

    return {"label": label, "params": base}


def execute_query_plan(df: pd.DataFrame, plan: dict[str, Any]) -> dict[str, Any]:
    params = plan["params"]
    summary = q_vehicle_component_summary(df, **params)
    samples = q_text_evidence_samples(df, limit=8, **params)
    comp_by_year = q_component_by_year(
        df,
        part_category=params.get("part_category"),
        make=params.get("make"),
        model=params.get("model"),
        year=params.get("year"),
    )
    surge = q_recent_surge(
        df,
        months=6,
        make=params.get("make"),
        model=params.get("model"),
        year=params.get("year"),
        part_category=params.get("part_category"),
        text_keywords=params.get("text_keywords") or None,
    )
    return {
        "plan_label": plan["label"],
        "params": params,
        "summary": summary,
        "samples": samples.to_dict("records"),
        "component_by_year": comp_by_year.to_dict("records"),
        "recent_surge": surge,
    }


def evaluate_step(hypothesis: dict[str, Any], step_result: dict[str, Any], *, is_last_iteration: bool) -> dict[str, Any]:
    """조회 결과를 판정한다. 결함 확정이 아니라 가설 지지/기각/보류만 한다."""
    h = dict(hypothesis)
    summary = step_result["summary"]
    samples = step_result["samples"]
    surge = step_result["recent_surge"]

    support_count = int(summary.get("text_match_count") or summary.get("component_count") or 0)
    component_count = int(summary.get("component_count") or 0)
    sample_count = len(samples)
    ratio = surge.get("ratio")
    surge_level = surge.get("surge_level")

    h["support_count"] = max(int(h.get("support_count") or 0), support_count)
    h["evidence_sample_count"] = max(int(h.get("evidence_sample_count") or 0), sample_count)
    h["surge_ratio"] = ratio
    h["surge_level"] = surge_level
    h["evidence_samples"] = samples[:5]

    step_trace = {
        "iteration": h["iterations"],
        "plan": step_result["plan_label"],
        "support_count": support_count,
        "component_count": component_count,
        "sample_count": sample_count,
        "surge_level": surge_level,
        "surge_ratio": ratio,
    }
    h["trace"] = [*h.get("trace", []), step_trace]

    strong_surge = False
    if ratio == float("inf"):
        strong_surge = True
    elif isinstance(ratio, (int, float)) and ratio >= STRONG_SURGE_RATIO:
        strong_surge = True

    # 기준 1: 반복 패턴 + 원문 샘플이 충분하면 지지.
    if support_count >= MIN_SUPPORT_COUNT and sample_count >= MIN_EVIDENCE_SAMPLES:
        h["status"] = STATUS_SUPPORTED
        h["decision_reason"] = (
            f"{step_result['plan_label']} 범위에서 관련 신고 {support_count}건, "
            f"원문 근거 {sample_count}건 확인"
        )
        if strong_surge:
            h["decision_reason"] += f", 최근 급증 신호({surge_level}, ratio={ratio}) 동반"
        return h

    # 기준 2: 원문 샘플은 적지만 부품 반복과 급증이 있으면 보류가 아니라 조사 후보로 지지.
    if component_count >= MIN_SUPPORT_COUNT and strong_surge and sample_count >= 1:
        h["status"] = STATUS_SUPPORTED
        h["decision_reason"] = (
            f"원문 샘플은 {sample_count}건이나 부품 범위 신고 {component_count}건 및 "
            f"급증 신호({surge_level}, ratio={ratio})가 있어 조사 후보로 유지"
        )
        return h

    # 마지막 반복 전이면 계속 완화.
    if not is_last_iteration:
        h["status"] = STATUS_PENDING
        h["decision_reason"] = (
            f"현재 범위 근거 부족: 관련 {support_count}건, 원문 {sample_count}건. "
            "다음 반복에서 조건 완화"
        )
        return h

    # 마지막 반복 후 종료.
    if component_count == 0 and support_count == 0:
        h["status"] = STATUS_REJECTED
        h["decision_reason"] = "완화 범위에서도 관련 부품/원문 패턴이 확인되지 않음"
    else:
        h["status"] = STATUS_INSUFFICIENT
        h["decision_reason"] = (
            f"관련 데이터는 있으나 최소 기준 미달: 관련 {support_count}건, "
            f"부품 {component_count}건, 원문 {sample_count}건"
        )
    return h


def investigate_one(record: dict[str, Any], df: pd.DataFrame, meta_index: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """JSONL 구조화 결과 1건에 대한 while 조사 루프."""
    hypo = build_hypothesis(record, meta_index)

    if not hypo["odino"]:
        hypo["status"] = STATUS_INSUFFICIENT
        hypo["decision_reason"] = "ODINO 없음"
        return hypo
    if hypo["insufficient_info"]:
        hypo["status"] = STATUS_INSUFFICIENT
        hypo["decision_reason"] = "구조화 단계에서 insufficient_info=True"
        return hypo
    if not hypo.get("make") or not hypo.get("model") or not hypo.get("year"):
        hypo["status"] = STATUS_INSUFFICIENT
        hypo["decision_reason"] = "CSV에서 차량 메타(make/model/year)를 찾지 못함"
        return hypo

    while hypo["status"] == STATUS_PENDING and hypo["iterations"] < MAX_ITER:
        hypo["iterations"] += 1
        plan = make_query_plan(hypo, hypo["iterations"])
        step = execute_query_plan(df, plan)
        hypo = evaluate_step(hypo, step, is_last_iteration=hypo["iterations"] >= MAX_ITER)

    if hypo["status"] == STATUS_PENDING:
        hypo["status"] = STATUS_INSUFFICIENT
        hypo["decision_reason"] = f"MAX_ITER({MAX_ITER}) 도달 후 미결"
    return hypo


def _flatten_result(result: dict[str, Any]) -> dict[str, Any]:
    keep = [
        "odino", "cmplid", "make", "model", "year", "fail_date", "ldate",
        "source_component", "part_category", "severity", "claim", "driving_context",
        "status", "iterations", "support_count", "evidence_sample_count",
        "surge_ratio", "surge_level", "decision_reason", "evidence_quote", "rule_notes",
    ]
    out = {k: result.get(k) for k in keep}
    out["text_keywords"] = json.dumps(result.get("text_keywords", []), ensure_ascii=False)
    out["trace_json"] = json.dumps(result.get("trace", []), ensure_ascii=False)
    out["evidence_samples_json"] = json.dumps(result.get("evidence_samples", []), ensure_ascii=False)
    return out


def run_investigation_loop(
    jsonl_path: str | Path | None = None,
    csv_path: str | Path | None = None,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    records = load_jsonl(jsonl_path)
    if limit is not None:
        records = records[:limit]
    df = load_processed(csv_path or DEFAULT_CSV_PATH)
    meta_index = _meta_by_odino(df)

    print(f"[INV-02 LOOP] start records={len(records)}")
    results: list[dict[str, Any]] = []
    for i, rec in enumerate(records, start=1):
        res = investigate_one(rec, df, meta_index)
        results.append(res)
        print(
            f"  {i:03d}/{len(records):03d} ODINO={res.get('odino')} "
            f"status={res.get('status')} support={res.get('support_count')} "
            f"reason={str(res.get('decision_reason'))[:90]}"
        )
    return results


def save_results(results: list[dict[str, Any]], out_path: str | Path | None = None) -> Path:
    if out_path is None:
        out = DEFAULT_OUT_PATH if DEFAULT_OUT_PATH.parent.exists() else FALLBACK_OUT_PATH
    else:
        out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df_out = pd.DataFrame([_flatten_result(r) for r in results])
    df_out.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[INV-03 SAVE] path={out} rows={len(df_out)} status={df_out['status'].value_counts().to_dict() if len(df_out) else {}}")
    return out


def run(
    jsonl_path: str | Path | None = None,
    csv_path: str | Path | None = None,
    out_path: str | Path | None = None,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    results = run_investigation_loop(jsonl_path=jsonl_path, csv_path=csv_path, limit=limit)
    save_results(results, out_path=out_path)
    return results


def investigate_ad_hoc(
    df: pd.DataFrame,
    *,
    make: str | None = None,
    model: str | None = None,
    year: int | str | None = None,
    part_category: str | None = None,
    text_keywords: list[str] | None = None,
) -> dict[str, Any]:
    """
    CHT-01에서 사용자 질문을 바로 조사할 때 쓰는 간단 루프.
    JSONL이 없어도 같은 기준으로 통계·근거·급증을 묶어 반환한다.
    """
    pseudo = {
        "odino": "ADHOC",
        "part_category": part_category or "ELECTRICAL_SYSTEM",
        "symptoms": text_keywords or [],
        "severity": "UNKNOWN",
        "evidence_quote": " ".join(text_keywords or []),
        "insufficient_info": False,
    }
    h = build_hypothesis(pseudo, {})
    h.update({"make": make, "model": model, "year": str(year) if year else None, "text_keywords": text_keywords or []})

    if not make and not model and not year and not text_keywords:
        return {
            "status": STATUS_INSUFFICIENT,
            "decision_reason": "질문에서 차량/연식/증상 범위를 충분히 추출하지 못했습니다.",
            "summary": {},
            "evidence_samples": [],
        }

    summary = q_vehicle_component_summary(
        df,
        make=make,
        model=model,
        year=year,
        part_category=part_category,
        text_keywords=text_keywords,
    )
    support_count = int(summary.get("text_match_count") or summary.get("component_count") or 0)
    samples = summary.get("evidence_samples", [])
    surge = summary.get("recent_surge", {})

    if support_count >= MIN_SUPPORT_COUNT and len(samples) >= 1:
        status = STATUS_SUPPORTED
        reason = f"질문 범위에서 관련 신고 {support_count}건과 원문 근거 {len(samples)}건을 확인했습니다."
    elif int(summary.get("base_count") or 0) == 0:
        status = STATUS_INSUFFICIENT
        reason = "해당 차량/연식 범위의 데이터가 없습니다."
    elif support_count == 0:
        status = STATUS_REJECTED
        reason = "질문 범위에서 해당 증상/부품 패턴이 확인되지 않았습니다."
    else:
        status = STATUS_INSUFFICIENT
        reason = f"일부 관련 데이터는 있으나 최소 근거 기준에 부족합니다. 관련 신고 {support_count}건."

    return {
        "status": status,
        "decision_reason": reason,
        "support_count": support_count,
        "surge_level": surge.get("surge_level"),
        "surge_ratio": surge.get("ratio"),
        "summary": summary,
        "evidence_samples": samples,
        "note": "미검증 소비자 신고 데이터 기반 조사 후보입니다. 결함 확정이 아닙니다.",
    }


if __name__ == "__main__":
    run(limit=None)
