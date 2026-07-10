#!/usr/bin/env python3
"""
str05_query_understanding.py — STR-05 사용자 질문 이해 (차종·증상 추출 + 되물음 루프)

역할: 한국어 사용자 입력에서 **차종**과 **증상** 두 가지만 추출한다.
  - 차종: carRegistry 27종의 영문 표기로 정규화 (STR 데이터/웹앱 조회와 매칭)
  - 증상: STR-01 symptoms 형식의 짧은 한국어 명사구
둘 중 하나라도 확인 안 되면 그 항목만 콕 집어 되물어, 두 개 다 확보될 때까지 반복(슬롯 기반).

설계 (슬롯 기반 = 방식 A):
  - LLM: "이번 발화 + 이미 확보한 슬롯"을 보고 차종/증상을 추출 (한 턴 판단)
  - 코드: 슬롯을 보관·병합하고, 상태(complete/need_*)를 확정하고, 루프를 돌림
    → 코드가 상태의 최종 결정권자. LLM이 상태를 틀려도 코드가 슬롯 기준으로 재판정.

웹앱 연동 지점 (STR 트랙 범위 밖, 통합 시 참고):
  - scripts/cht01_chat_pipeline.py 의 parse_question() (규칙 기반, "TODO: LLM_CALL 교체 지점")
    자리에 extract_slots()를 꽂으면 됨. 반환의 차종(영문)으로 기존 DB 조회에 연결.
  - 되물음 왕복은 웹앱 채팅 UI가 need_* 상태일 때 후속질문을 띄우고 사용자 답을 다시 넣는 방식.

LLM 제공사는 str01_batch_structurize.py와 동일하게 PROVIDER 환경변수로 교체 가능(gemini | anthropic).
표준 라이브러리만 사용.

사용:
  python scripts/str05_query_understanding.py            # 내장 테스트 케이스 실행
  (모듈로 import: from str05_query_understanding import extract_slots, run_dialog)
"""
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = REPO_ROOT / "docs" / "str05_query_prompt.md"
RATE_LIMIT_WAITS = [15, 30, 60]
MAX_NO_PROGRESS = 2  # P2: 진전 없는 되물음이 이 횟수를 넘으면 포기(무한 루프 방지)

# carRegistry 27종 (영문 → 한국어 표시). 웹앱 백엔드와 동일한 정본.
CAR_MODELS = {
    "ACCENT": "엑센트", "ELANTRA": "아반떼", "IONIQ 5": "아이오닉5", "IONIQ 6": "아이오닉6",
    "KONA": "코나", "NEXO": "넥쏘", "PALISADE": "팰리세이드", "SANTA CRUZ": "싼타크루즈",
    "SANTA FE": "싼타페", "SONATA": "쏘나타", "TUCSON": "투싼", "VELOSTER": "벨로스터",
    "VENUE": "베뉴", "CARNIVAL": "카니발", "EV6": "EV6", "EV9": "EV9", "FORTE": "포르테",
    "K5": "K5", "NIRO": "니로", "NIRO EV": "니로EV", "RIO": "리오", "SELTOS": "셀토스",
    "SORENTO": "쏘렌토", "SOUL": "쏘울", "SPORTAGE": "스포티지", "STINGER": "스팅어",
    "TELLURIDE": "텔루라이드",
}


def load_env() -> dict:
    env = {}
    p = REPO_ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


# ── LLM 호출 (str01과 동일 패턴, provider 교체 가능) ──────────────────
def _post_json(url, body, headers):
    data = json.dumps(body).encode()
    for i, wait in enumerate([0] + RATE_LIMIT_WAITS):
        if wait:
            time.sleep(wait)
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and i < len(RATE_LIMIT_WAITS):
                continue
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:200]}")
    raise RuntimeError("rate limit 백오프 소진")


def call_llm(prompt, env):
    provider = env.get("PROVIDER", "gemini")
    if provider == "gemini":
        model = env.get("GEMINI_MODEL", "gemini-2.5-flash")
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={env['GEMINI_API_KEY']}")
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
        return _post_json(url, body, {})["candidates"][0]["content"]["parts"][0]["text"]
    if provider == "anthropic":
        body = {"model": env.get("ANTHROPIC_MODEL", "claude-sonnet-5"),
                "max_tokens": 1024, "messages": [{"role": "user", "content": prompt}]}
        headers = {"x-api-key": env["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"}
        resp = _post_json("https://api.anthropic.com/v1/messages", body, headers)
        return next(b["text"] for b in resp["content"] if b["type"] == "text")
    raise ValueError(f"지원하지 않는 PROVIDER: {provider}")


# ── 한 턴 추출 (LLM) ─────────────────────────────────────────────────
def _llm_extract(user_text, slots, base_prompt, env):
    known = []
    if slots.get("차종"):
        known.append(f"차종={slots['차종']}({slots.get('차종_표시','')})")
    if slots.get("증상"):
        known.append(f"증상={slots['증상']}")
    known_str = f"[이미 확보: {', '.join(known)}]\n" if known else ""
    prompt = f"{base_prompt}\n\n---\n\n{known_str}사용자 입력: {user_text}"
    raw = call_llm(prompt, env)
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    return json.loads(raw)


# ── 슬롯 병합 + 상태 확정 (코드가 최종 결정) ─────────────────────────
# 병합 원칙(P1 정정 반영): LLM이 이번 턴에 낸 non-null 값은 기존 값을 덮어쓴다
#   (정정 지원). LLM이 null을 내면 기존 값을 유지한다(LLM이 실수로 흘리는 것 방지).
def _merge_and_status(slots, ext):
    """LLM 추출을 슬롯에 병합. 코드가 상태를 재판정."""
    # 차종: 27종에 실제로 있는 값이면 덮어쓰기(정정 지원). null이면 기존 유지.
    cand = ext.get("차종")
    if cand in CAR_MODELS:
        slots["차종"] = cand
        slots["차종_표시"] = CAR_MODELS[cand]  # 표시명은 정본으로 강제(LLM 오타 방지)
    # 증상: non-null이면 덮어쓰기(정정 지원). null이면 기존 유지.
    if ext.get("증상"):
        slots["증상"] = str(ext["증상"]).strip()

    has_v, has_s = bool(slots.get("차종")), bool(slots.get("증상"))
    if has_v and has_s:
        status = "complete"
    elif not has_v and not has_s:
        status = "need_둘다"
    elif not has_v:
        status = "need_차종"
    else:
        status = "need_증상"
    return status


def _followup_question(status, slots, ext):
    """후속질문: LLM 제안을 쓰되, 없으면 상태 기반 템플릿으로 보장."""
    q = ext.get("후속질문")
    if q and status != "complete":
        return q
    if status == "need_차종":
        return f"'{slots.get('증상','')}' 증상이 있는 차량의 차종을 알려주시겠어요?"
    if status == "need_증상":
        return f"{slots.get('차종_표시','')}의 어떤 증상인지 구체적으로 알려주시겠어요?"
    if status == "need_둘다":
        return "어떤 차종이고, 어떤 증상이 있으신가요?"
    return None


def confirm_sentence(slots):
    return f"{slots['차종_표시']} / {slots['증상']}(으)로 이해했어요. 맞나요?"


# ── 공개 API: 한 턴 처리 ─────────────────────────────────────────────
def _filled_count(slots):
    return int(bool(slots.get("차종"))) + int(bool(slots.get("증상")))


def extract_slots(user_text, slots=None, base_prompt=None, env=None):
    """한 턴 처리. 반환: (갱신된 slots, 결과 dict).
    결과 dict = {차종, 차종_표시, 증상, 상태, 후속질문, 확인문장, 안내문}
    웹앱 연동 시 이 함수를 parse_question() 자리에 사용.
    P2: 진전 없는 되물음이 MAX_NO_PROGRESS를 넘으면 상태="unresolved"로 종료."""
    slots = dict(slots or {})
    env = env or load_env()
    base_prompt = base_prompt or PROMPT_PATH.read_text(encoding="utf-8")

    before = _filled_count(slots)
    ext = _llm_extract(user_text, slots, base_prompt, env)
    status = _merge_and_status(slots, ext)
    after = _filled_count(slots)

    # P2: 이번 턴에 새로 채워진 게 없고 아직 미완이면 무진전 카운트 증가
    if status != "complete":
        if after > before:
            slots["_no_progress"] = 0
        else:
            slots["_no_progress"] = slots.get("_no_progress", 0) + 1
    else:
        slots["_no_progress"] = 0

    guide = None
    if status != "complete" and slots.get("_no_progress", 0) >= MAX_NO_PROGRESS:
        # 같은 항목을 반복해서 물어도 안 채워짐 → 포기하고 안내
        status = "unresolved"
        got = []
        if slots.get("차종_표시"):
            got.append(f"차종은 {slots['차종_표시']}")
        if slots.get("증상"):
            got.append(f"증상은 {slots['증상']}")
        got_str = ", ".join(got) if got else "확인된 정보가 없어요"
        guide = (f"입력만으로는 차종과 증상을 모두 확인하지 못했어요({got_str}). "
                 f"차종명과 구체적인 증상을 한 번에 알려주시면 도와드릴게요.")

    result = {
        "차종": slots.get("차종"),
        "차종_표시": slots.get("차종_표시"),
        "증상": slots.get("증상"),
        "상태": status,
        "후속질문": _followup_question(status, slots, ext) if status not in ("complete", "unresolved") else None,
        "확인문장": confirm_sentence(slots) if status == "complete" else None,
        "안내문": guide,
    }
    return slots, result


# ── 다중 턴 대화 시뮬레이션 (테스트용) ───────────────────────────────
def run_dialog(user_turns, env=None, base_prompt=None, verbose=True):
    """user_turns: 사용자가 순서대로 입력할 발화 리스트.
    되물음이 나오면 다음 발화로 답한다고 가정하고 슬롯이 찰 때까지 진행."""
    slots = {}
    transcript = []
    for i, text in enumerate(user_turns, 1):
        slots, res = extract_slots(text, slots, base_prompt, env)
        transcript.append({"turn": i, "user": text, "result": res})
        if verbose:
            print(f"  [{i}턴] 사용자: {text}")
            print(f"        → 차종={res['차종']} 증상={res['증상']} 상태={res['상태']}")
            if res["후속질문"]:
                print(f"        ← 되물음: {res['후속질문']}")
            if res["확인문장"]:
                print(f"        ← 확인: {res['확인문장']}")
            if res.get("안내문"):
                print(f"        ← 안내(종료): {res['안내문']}")
        if res["상태"] in ("complete", "unresolved"):
            break
    return slots, transcript


# ── 내장 테스트 케이스 ───────────────────────────────────────────────
TEST_CASES = [
    ("둘 다 명확", ["투싼 계기판 깜빡임"]),
    ("증상만 → 차종 되물음 → 답변", ["계기판이 자꾸 껌뻑거려요", "아이오닉5요"]),
    ("차종만 → 증상 되물음 → 답변", ["쏘렌토가 좀 이상해요", "시동이 안 걸려요"]),
    ("둘 다 없음 → 되물음 → 순차 답변", ["차가 문제가 있어요", "투싼이요", "충전이 안 돼요"]),
    ("영어/오타 별칭 정규화", ["ioniq5 충전 불가"]),
    ("등록 밖 차종", ["제네시스 G80 계기판 이상"]),
]


def main():
    env = load_env()
    base_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    print(f"PROVIDER={env.get('PROVIDER','gemini')}, MODEL={env.get('GEMINI_MODEL','gemini-2.5-flash')}\n")
    results = []
    for name, turns in TEST_CASES:
        print(f"=== {name} ===")
        slots, transcript = run_dialog(turns, env, base_prompt)
        final = transcript[-1]["result"]
        ok = final["상태"] == "complete" or name == "등록 밖 차종"
        print(f"  최종: 차종={final['차종']} / 증상={final['증상']} / 상태={final['상태']}\n")
        results.append({"case": name, "turns": turns, "transcript": transcript,
                        "final": final})
    out = REPO_ROOT / "data" / "processed" / "str05_test_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"테스트 결과 저장: {out}")


if __name__ == "__main__":
    main()
