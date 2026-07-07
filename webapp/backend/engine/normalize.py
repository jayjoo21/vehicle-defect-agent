"""차종명 정규화. scripts/precision_v2.py의 normalize_model()을 그대로 재사용(중복 구현 금지)."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.precision_v2 import normalize_model  # noqa: E402

__all__ = ["normalize_model"]
