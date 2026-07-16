"""GET /api/parts/{part_number}/related — 부품 계열(family) 공유 차종·리콜 확장 조회.

data/processed/rcl573_components_normalized.csv(이미 확정된 Part 573 원문+공급사
정규화 산출물, CLAUDE.md 기록 참조)만을 데이터 소스로 한다 — 새 정규화 로직·DB 스키마
변경 없음. part_family는 scripts/rcl573_shared_parts.py와 동일하게 부품번호 앞 5자리로
정의한다. affected_models(캠페인·부품번호별 실제 적용 차종·연식 원문)를 그대로 펼쳐
(model, campaign, part_number) 튜플을 만들고, 차종명은 engine.normalize.normalize_model로
정규화한다(다른 라우터와 동일한 base_model 기준).
"""
import csv
import re
import sys
from pathlib import Path

from fastapi import APIRouter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.normalize import normalize_model

router = APIRouter(prefix="/parts", tags=["parts"])

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPONENTS_CSV = REPO_ROOT / "data" / "processed" / "rcl573_components_normalized.csv"

YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def _load_rows() -> list[dict]:
    with open(COMPONENTS_CSV, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


_ROWS = _load_rows()


def _split_model_year(token: str) -> str:
    tokens = token.strip().split()
    if tokens and YEAR_RE.match(tokens[-1]):
        return " ".join(tokens[:-1])
    return token.strip()


@router.get("/{part_number}/related")
def get_related_parts(part_number: str):
    part_number = part_number.strip()
    family = part_number[:5].upper()

    campaigns_in_family: set[str] = set()
    supplier_group_counts: dict[str, int] = {}
    shared: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for row in _ROWS:
        pn = (row.get("part_number") or "").strip()
        if len(pn) < 5 or pn[:5].upper() != family:
            continue
        campaign = row["campaign"]
        campaigns_in_family.add(campaign)
        sg = row.get("supplier_group") or None
        if sg:
            supplier_group_counts[sg] = supplier_group_counts.get(sg, 0) + 1

        for token in (row.get("affected_models") or "").split(";"):
            model_raw = _split_model_year(token)
            if not model_raw:
                continue
            base_model = normalize_model(model_raw)
            key = (base_model, campaign)
            if key in seen:
                continue
            seen.add(key)
            shared.append({"model": base_model, "campaign": campaign, "part_number": pn})

    # 부품 계열 안에 캠페인이 하나뿐이면(=이 부품이 다른 리콜과 공유되지 않음) "공유 없음"으로
    # 정직하게 빈 리스트를 반환한다 — 자기 자신의 차종 목록만 나열하는 건 확장이 아니다.
    if len(campaigns_in_family) <= 1:
        shared = []

    supplier_group = max(supplier_group_counts, key=supplier_group_counts.get) if supplier_group_counts else None

    return {
        "part_number": part_number,
        "part_family": family,
        "supplier_group": supplier_group,
        "shared": shared,
    }
