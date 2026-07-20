#!/usr/bin/env python3
"""
str_structurize_v3.py — 백엔드가 바로 가져다 쓰는 v3 구조화 단일 진입점

STR-01(str01_batch_structurize.py)이 "CSV 여러 건을 배치로" 처리하는 CLI 도구라면,
이 파일은 "신고 1건을 받으면 구조화된 dict 하나를 즉시 반환"하는 함수 인터페이스만
제공한다. 배치 파일 I/O·이어하기·--prompt 인자 같은 CLI 전용 개념은 없고, v3
스키마(8필드, mentions_existing_recall 포함)로 고정돼 있다.

내부 로직(LLM 호출·스키마 검증·인용 환각 검사·재시도)은 str01_batch_structurize.py를
그대로 재사용한다 — 같은 검증 규칙을 두 곳에 중복 유지하지 않기 위함.

백엔드 사용 예:
    from scripts.str_structurize_v3 import structurize
    result = structurize(odino="11732905", cdescr="THE VEHICLE...")
    # result = {"odino": ..., "part_category": ..., ..., "mentions_existing_recall": bool}

CLI로 단건 테스트도 가능:
    python3 scripts/str_structurize_v3.py "TEST-1" "THE ADAS SUDDENLY DISENGAGED..."
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from str01_batch_structurize import structurize_one, load_env, fix_mojibake  # noqa: E402

PROMPT_V3_PATH = REPO_ROOT / "docs" / "struct_prompt_v3.md"
_PROMPT_V3 = PROMPT_V3_PATH.read_text(encoding="utf-8")
EXTRA_BOOL_KEYS = frozenset({"mentions_existing_recall"})


def structurize(odino: str, cdescr: str, env: dict = None) -> dict:
    """신고 1건(odino, CDESCR 원문)을 v3 스키마(8필드)로 구조화해 dict로 반환.

    env를 안 넘기면 REPO_ROOT/.env에서 자동 로드(GEMINI_API_KEY 등 — 매 호출마다
    다시 읽지 않으려면 호출부에서 load_env()로 한 번 로드해 넘기는 걸 권장).
    최대 3회 재시도 후에도 검증(스키마·인용)을 통과 못 하면 ValueError.
    """
    env = env if env is not None else load_env()
    cdescr = fix_mojibake(cdescr)
    rec, stats = structurize_one(str(odino), cdescr, _PROMPT_V3, env, EXTRA_BOOL_KEYS)
    if rec is None:
        raise ValueError(f"구조화 실패(odino={odino}): {stats['errors']}")
    return rec


if __name__ == "__main__":
    import json

    odino_arg = sys.argv[1] if len(sys.argv) > 1 else "TEST-1"
    cdescr_arg = sys.argv[2] if len(sys.argv) > 2 else (
        "THE VEHICLE'S ADAPTIVE CRUISE CONTROL SUDDENLY DISENGAGED WHILE DRIVING ON THE HIGHWAY "
        "AT 65 MPH. THE DASHBOARD SHOWED A WARNING LIGHT. THIS HAS HAPPENED 3 TIMES."
    )
    print(json.dumps(structurize(odino_arg, cdescr_arg), ensure_ascii=False, indent=2))
