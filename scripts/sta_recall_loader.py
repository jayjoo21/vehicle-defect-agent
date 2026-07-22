"""
STA-01/02 보조 모듈 — RCL573 파이프라인 산출물을 recall_records에 적재
============================================================
배경
- 기존 STA-02 판정(find_matching_recall)은 리콜 이력을 register_recall()로
  수동 등록하거나, PART_RECALL_KEYWORDS라는 카테고리별 키워드 사전으로
  "리콜이 있을 법하다"를 추측하는 수준이었다.
- RCL573 파이프라인(rcl573_fetch.py -> rcl573_parse.py -> rcl573_supplier_normalize.py
  -> rcl573_apply_alias.py)이 완성되면서 실제 NHTSA Part 573 리콜의
  campaign × part_number × 부품명 × 적용 모델/연식 데이터
  (data/processed/rcl573_components_normalized.csv)를 쓸 수 있게 됐다.
- 이 모듈은 그 산출물을 recall_records 테이블에 적재하는 "어댑터" 역할만 한다.
  DB insert/UPSERT 로직은 새로 만들지 않고 기존 register_recall()을 그대로
  재사용한다(검증된 vehicle 매칭·충돌 처리 로직 중복 방지, DRY).

✅ recall_date 결측 — 2026-07-13 발견, 같은 날 rcl573_parse.py에서 수정됨
    rcl573_flatfile_components.csv(1단계 산출물)에는 RCDATE(리콜일) 컬럼이 있었는데,
    rcl573_parse.py의 build_final_csv()가 최종 CSV를 만들 때 그 컬럼을 자기
    OUT_COLS 목록에 빠뜨려서 recall_date가 통째로 소실되고 있었다(실물 확인).
    → rcl573_parse.py의 OUT_COLS에 "recall_date" 한 줄을 추가해 원본 수정 완료.

    이 로더는 그 수정된 recall_date 컬럼이 있으면 그대로 읽어서 register_recall()에
    넘긴다(같은 캠페인의 여러 part_number 행이 섞여도 날짜는 보통 하나라 min()으로
    안전하게 대표값을 고른다). 다만 rcl573_parse.py를 아직 재실행하지 않은 예전
    rcl573_components_normalized.csv(recall_date 컬럼 자체가 없는 파일)를 이 로더에
    넣어도 죽지 않는다 — 컬럼이 없으면 row.get()이 빈 문자열을 주고, 그러면
    recall_date=None으로 안전하게 적재된다(과거와 동일한 폴백 동작 유지).

MAKE 추론 — affected_models에는 차종명만 있고 제조사가 없음
    rcl573_components_normalized.csv의 affected_models는 "TUCSON 2025; TUCSON 2024"
    처럼 "모델 연식" 쌍의 세미콜론 목록만 준다. 제조사는 아래 MODEL_TO_MAKE
    표(cht01_chat_pipeline.py의 MODEL_ALIASES 27종 + rcl573 스크립트 주석에
    등장하는 모델 기준)로 추론한다. 표에 없는 모델은 임의로 추측하지 않고
    make=UNKNOWN으로 적재한 뒤 콘솔에 목록으로 보고한다 — rcl573_apply_alias.py의
    "alias에 없는 raw_name은 임의로 채우지 않고 콘솔에 보고" 원칙과 동일하게 맞췄다.

사용법
    from sta01_02_status_tracking import get_conn, init_db
    from sta_recall_loader import load_rcl573_recalls
    conn = init_db()
    load_rcl573_recalls(conn)   # 기본 경로: data/processed/rcl573_components_normalized.csv
"""
from __future__ import annotations

import csv
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from sta01_02_status_tracking import register_recall

DEFAULT_COMPONENTS_CSV = Path("data/processed/rcl573_components_with_compdesc1.csv")
DEFAULT_SHARED_PARTS_CSV = Path("data/processed/shared_parts.csv")
RCL_FALLBACKS = {
    # 2026-07-21 신규(설계 한계 C 돌파): rcl573_classify_compdesc.py가 만드는
    # compdesc1 분류 붙은 파일을 기본으로 쓰되, 아직 그 분류를 안 돌렸거나
    # 파일이 없는 환경에서도 죽지 않도록 원본(compdesc1 없음)을 폴백으로 남겨둔다
    # — 이 경우 register_recall()에 compdesc1=None이 전달되고,
    # sta01_02_status_tracking.py의 _recall_matches()가 자동으로 기존 키워드
    # 휴리스틱(COMPDESC1_RECALL_KEYWORDS)으로 폴백한다.
    "components": [
        Path("data/processed/rcl573_components_normalized.csv"),
        Path("/mnt/data/rcl573_components_with_compdesc1.csv"),
        Path("/mnt/data/rcl573_components_normalized.csv"),
        Path("rcl573_components_with_compdesc1.csv"),
        Path("rcl573_components_normalized.csv"),
    ],
    "shared_parts": [Path("/mnt/data/shared_parts.csv"), Path("shared_parts.csv")],
}

# cht01_chat_pipeline.MODEL_ALIASES 27종 + rcl573 스크립트 주석(Telluride/Sportage/
# Cadenza 등)에 나온 모델 기준. 여기 없는 모델은 make=UNKNOWN으로 적재되고 콘솔에
# 보고된다 — 실행 로그에서 발견하면 이 표에 바로 추가할 것.
MODEL_TO_MAKE: dict[str, str] = {
    "TUCSON": "HYUNDAI", "SANTA FE": "HYUNDAI", "SONATA": "HYUNDAI", "ELANTRA": "HYUNDAI",
    "KONA": "HYUNDAI", "IONIQ 5": "HYUNDAI", "IONIQ5": "HYUNDAI", "PALISADE": "HYUNDAI",
    "VENUE": "HYUNDAI", "ACCENT": "HYUNDAI", "NEXO": "HYUNDAI",
    "SORENTO": "KIA", "SPORTAGE": "KIA", "FORTE": "KIA", "SOUL": "KIA", "TELLURIDE": "KIA",
    "CADENZA": "KIA", "K5": "KIA", "K8": "KIA", "K9": "KIA", "NIRO": "KIA", "SELTOS": "KIA",
    "CARNIVAL": "KIA", "STINGER": "KIA", "RIO": "KIA", "EV9": "KIA",
    # 2026-07-15 효선 추가 — 실행 로그에서 발견된 미매핑 25종
    "CARNIVAL HYBRID": "KIA",
    "ELANTRA HYBRID": "HYUNDAI",
    "ELANTRA N": "HYUNDAI",
    "EV6": "KIA",
    "GV60": "GENESIS",
    "GV70 ELECTRIFIED": "GENESIS",
    "IONIQ 6": "HYUNDAI",
    "IONIQ 9": "HYUNDAI",
    "IONIQ ELECTRIC": "HYUNDAI",
    "K4": "KIA",
    "K900": "KIA",
    "KONA ELECTRIC": "HYUNDAI",
    "NIRO EV": "KIA",
    "NIRO PHEV": "KIA",
    "PALISADE HYBRID": "HYUNDAI",
    "SANTA CRUZ": "HYUNDAI",
    "SANTA FE HYBRID": "HYUNDAI",
    "SANTA FE PLUG-IN HYBRID": "HYUNDAI",
    "SONATA HYBRID": "HYUNDAI",
    "SORENTO HYBRID": "KIA",
    "SORENTO PHEV": "KIA",
    "SPORTAGE HYBRID": "KIA",
    "SPORTAGE PHEV": "KIA",
    "TUCSON HYBRID": "HYUNDAI",
    "TUCSON PLUG-IN HYBRID": "HYUNDAI",
}

AFFECTED_MODEL_RE = re.compile(r"^(.*\S)\s+(\d{4})$")


def _split_multi(cell: str | None) -> list[str]:
    return [x.strip() for x in (cell or "").split(";") if x.strip()]


def parse_affected_models(cell: str | None) -> list[tuple[str, str]]:
    """'TUCSON 2025; TUCSON 2024' -> [('TUCSON','2025'), ('TUCSON','2024')].
    패턴에 안 맞는 항목도 버리지 않고 (원문 그대로, '') 형태로 보존한다
    (rcl573_apply_alias.py와 동일한 "정보 손실 방지" 원칙)."""
    out = []
    for token in _split_multi(cell):
        m = AFFECTED_MODEL_RE.match(token)
        if m:
            out.append((m.group(1).strip().upper(), m.group(2)))
        else:
            out.append((token.upper(), ""))
    return out


def _resolve_optional(path: str | Path | None, default: Path, fallbacks: list[Path]) -> Path | None:
    for candidate in [path, default, *fallbacks]:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def build_part_family_map(shared_parts_csv: str | Path | None = None) -> dict[str, str]:
    """part_number -> part_family 역색인을 만든다. shared_parts.csv가 없으면
    빈 dict를 반환하고 적재는 계속 진행한다(보강 정보일 뿐 필수 아님)."""
    path = _resolve_optional(shared_parts_csv, DEFAULT_SHARED_PARTS_CSV, RCL_FALLBACKS["shared_parts"])
    mapping: dict[str, str] = {}
    if not path:
        print("[STA RECALL] shared_parts.csv 없음 — part_family 보강 생략(리콜 적재는 계속 진행)")
        return mapping
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            fam = (row.get("part_family") or "").strip()
            if not fam:
                continue
            for pn in _split_multi(row.get("part_numbers")):
                mapping[pn] = fam
    print(f"[STA RECALL] part_family 매핑 {len(mapping):,}개 부품번호 로드 ({path})")
    return mapping


def load_rcl573_recalls(
    conn: sqlite3.Connection,
    components_csv: str | Path | None = None,
    shared_parts_csv: str | Path | None = None,
) -> dict[str, Any]:
    """rcl573_components_normalized.csv를 읽어 recall_records에 적재한다.

    반환: {"source_rows", "recall_records_loaded", "rows_without_affected_models",
           "unmapped_models"} 요약 dict — 실행 로그/리포트에 그대로 쓰기 좋게 설계.
    """
    path = _resolve_optional(components_csv, DEFAULT_COMPONENTS_CSV, RCL_FALLBACKS["components"])
    if not path:
        raise FileNotFoundError(
            f"rcl573_components_normalized.csv를 찾을 수 없습니다: "
            f"{components_csv or DEFAULT_COMPONENTS_CSV} (RCL573 파이프라인을 먼저 실행했는지 확인하세요)"
        )
    part_family_map = build_part_family_map(shared_parts_csv)

    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # recall_records는 UNIQUE(vehicle_id, campaign_no) 제약이라, 같은 캠페인 안의
    # 여러 part_number 행(정규화 단계에서 "부품번호 1개 = 1행"으로 이미 분해됨)은
    # 하나의 레코드로 묶어야 한다 — 세미콜론 join은 이 프로젝트 기존 관례
    # (rcl573_shared_parts.py의 part_numbers 컬럼과 동일한 방식).
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = defaultdict(lambda: {
        "part_numbers": [], "component_names": set(), "component_descs": set(), "defect_causes": set(),
        "recall_dates": set(), "compdesc1_values": set(),
    })
    unmapped_models: set[str] = set()
    n_no_affected_models = 0

    for row in rows:
        campaign = (row.get("campaign") or "").strip()
        if not campaign:
            continue
        affected = parse_affected_models(row.get("affected_models"))
        if not affected:
            n_no_affected_models += 1
            continue

        pn = (row.get("part_number") or "").strip()
        comp_name = (row.get("component_name") or "").strip()
        comp_desc = (row.get("component_desc") or "").strip()
        defect_cause = (row.get("defect_cause") or "").strip()
        # recall_date 컬럼이 아예 없는 구버전 CSV여도 .get()이 빈 문자열을 주므로 안전.
        recall_date = (row.get("recall_date") or "").strip()
        # 2026-07-21 신규: compdesc1 컬럼이 없는 구버전 CSV(rcl573_components_
        # normalized.csv)를 넣어도 .get()이 빈 문자열을 주므로 안전 — 이 경우
        # register_recall()에 compdesc1=None이 전달되고 아래에서 자동으로
        # 키워드 휴리스틱 폴백 경로로 빠진다.
        compdesc1 = (row.get("compdesc1") or "").strip()

        for model, year in affected:
            make = MODEL_TO_MAKE.get(model)
            if not make:
                unmapped_models.add(model)
                make = "UNKNOWN"
            key = (make, model, year, campaign)
            g = groups[key]
            if pn:
                g["part_numbers"].append(pn)
            if comp_name:
                g["component_names"].add(comp_name)
            if comp_desc:
                g["component_descs"].add(comp_desc)
            if defect_cause:
                g["defect_causes"].add(defect_cause)
            if recall_date:
                g["recall_dates"].add(recall_date)
            if compdesc1:
                g["compdesc1_values"].add(compdesc1)

    n_loaded = 0
    n_with_recall_date = 0
    n_with_compdesc1 = 0
    for (make, model, year, campaign), g in groups.items():
        component = "; ".join(sorted(g["component_names"])) or "; ".join(sorted(g["component_descs"])) or "UNKNOWN"
        summary = "; ".join(sorted(g["defect_causes"]))[:500]
        part_numbers_joined = "; ".join(sorted(set(g["part_numbers"]))) or None
        families = {part_family_map[pn] for pn in g["part_numbers"] if part_family_map.get(pn)}
        part_family = "; ".join(sorted(families)) or None
        # 같은 캠페인은 리콜일이 원래 하나여야 정상이라 min()으로 대표값을 고른다
        # (YYYYMMDD 문자열은 사전순 정렬이 곧 날짜순 정렬이라 min이 가장 이른 날짜).
        recall_date = min(g["recall_dates"]) if g["recall_dates"] else None
        if recall_date:
            n_with_recall_date += 1
        # 2026-07-21 신규: 같은 캠페인의 여러 부품번호 행은 rcl573_classify_
        # compdesc.py가 캠페인 단위로 분류하므로 compdesc1_values가 정상적으로는
        # 값 1개짜리 집합이어야 한다. 혹시 여러 값이 섞여 있으면(데이터 이상)
        # 임의로 하나를 고르지 않고 정직하게 None으로 둬서 폴백 경로를 타게 한다
        # — 틀린 값 하나를 확신 있게 쓰는 것보다 "모르겠다"가 안전하다.
        compdesc1 = next(iter(g["compdesc1_values"])) if len(g["compdesc1_values"]) == 1 else None
        if compdesc1:
            n_with_compdesc1 += 1

        register_recall(
            conn,
            make=make,
            model=model,
            year=year or None,
            campaign_no=campaign,
            recall_date=recall_date,
            component=component,
            compdesc1=compdesc1,
            summary=summary,
            source="RCL573",
            status="OPEN",
            part_number=part_numbers_joined,
            part_family=part_family,
        )
        n_loaded += 1

    result = {
        "source_rows": len(rows),
        "recall_records_loaded": n_loaded,
        "recall_records_with_recall_date": n_with_recall_date,
        "recall_records_with_compdesc1": n_with_compdesc1,
        "rows_without_affected_models": n_no_affected_models,
        "unmapped_models": sorted(unmapped_models),
    }
    print(
        f"[STA RECALL] {path.name} -> recall_records {n_loaded:,}건 적재 "
        f"(원본 {len(rows):,}행, affected_models 없음 {n_no_affected_models}행, "
        f"recall_date 있음 {n_with_recall_date}/{n_loaded}건, "
        f"compdesc1 있음 {n_with_compdesc1}/{n_loaded}건)"
    )
    if n_loaded and n_with_recall_date == 0:
        print(
            "[STA RECALL][INFO] recall_date가 전부 비어 있습니다 — rcl573_parse.py를 "
            "아직 재실행하지 않은 예전 CSV일 수 있습니다(2026-07-13 수정분 반영 전)."
        )
    if n_loaded and n_with_compdesc1 == 0:
        print(
            "[STA RECALL][INFO] compdesc1이 전부 비어 있습니다 — rcl573_classify_compdesc.py를 "
            "아직 실행하지 않은 원본 CSV(rcl573_components_normalized.csv)일 수 있습니다. "
            "이 경우 리콜 매칭은 자동으로 기존 키워드 휴리스틱(COMPDESC1_RECALL_KEYWORDS)으로 "
            "동작합니다 — 기능이 멈추진 않지만 정확도가 떨어집니다."
        )
    if unmapped_models:
        print(
            f"[STA RECALL][WARN] MODEL_TO_MAKE에 없는 모델 {len(unmapped_models)}개 "
            f"(make=UNKNOWN으로 적재됨, 확인 후 표에 추가 필요): {sorted(unmapped_models)}"
        )
    return result


if __name__ == "__main__":
    from sta01_02_status_tracking import init_db

    conn0 = init_db()
    print(load_rcl573_recalls(conn0))
    conn0.close()
