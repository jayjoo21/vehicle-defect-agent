"""내 차(MyCar) 핫스팟 6개 도메인 분류.

recalls.component/summary, complaints.part_category 텍스트에 대한 키워드 기반 근사 매핑.
COMPDESC/Component 라벨은 부정확할 수 있다는 프로젝트 원칙(CLAUDE.md)과 같은 이유로,
이 매핑도 완전하지 않은 근사치임을 API 응답에 함께 표기한다(mapping_basis 필드).
실데이터에 매칭되는 것이 없으면 절대 임의로 채우지 않고 'new'(회색/이력 없음)로 둔다.
"""
import re

DOMAINS = [
    "계기판",
    "인포테인먼트",
    "ICCU_충전제어",
    "구동배터리",
    "ADAS_카메라",
    "제동SW",
]

_KEYWORDS = {
    "계기판": ["INSTRUMENT CLUSTER", "INSTRUMENT_CLUSTER", "계기판"],
    "인포테인먼트": ["INFOTAINMENT", "인포테인먼트", "AVN"],
    "ICCU_충전제어": ["CHARGING", "ICCU", "충전"],
    "구동배터리": ["TRACTION BATTERY", "PROPULSION_BATTERY", "배터리관리시스템", "BMS", "구동배터리", "BATTERY"],
    "ADAS_카메라": ["ADAS", "CAMERA", "카메라", "전방충돌", "BACK OVER PREVENTION", "차선"],
    "제동SW": ["BRAKE", "제동", "HYDRAULIC:POWER ASSIST"],
}


def classify_domain(text: str) -> str | None:
    if not text:
        return None
    upper = text.upper()
    for domain, keywords in _KEYWORDS.items():
        for kw in keywords:
            if kw.upper() in upper:
                return domain
    return None
