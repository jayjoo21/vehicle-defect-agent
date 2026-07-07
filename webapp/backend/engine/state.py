"""여러 파워트레인 변형(base_model 동일)의 월별 state를 하나의 대표 state로 합치는 공용 규칙.
signals.py(카드/히트맵)와 vehicles.py(history)가 함께 사용한다."""

STATE_PRIORITY = {"recalled": 4, "active": 3, "rising": 2, "new": 1, "resolved": 0}


def top_state(states) -> str:
    return max(states, key=lambda s: STATE_PRIORITY[s])
