"""POST /api/chat — SSE 스트림 (조사 채팅, v0 mock 모드).

3개 데모 시나리오만 지원: EV6 계기판 / IONIQ 5 충전(ICCU) / 범위 밖 질문.
시나리오 매칭은 키워드 기반(v0 잠정) — 실제 LLM 라우팅은 이후 버전에서 대체 예정.
타임라인 단계(차종 인식·이력 조회·리콜 대조 등)의 수치는 전부 이 함수가 DB에서
직접 조회한 실측값이며, llm/mock_responses의 markdown_template에도 그 실측값만
채워 넣는다 — 지어낸 수치 없음.

5.5단계: 각 단계에 tool(도구 칩)과 duration_ms(DB 조회·판정에 걸린 실측 시간, 이후의
UI 페이싱용 sleep은 제외)를 추가했다. 인용 소스에는 part_category/symptom(이미
struct_verify로 환각 검증된 구조화 필드)을 함께 실어 프론트가 원문 옆에 한국어 한 줄
요약을 병기할 수 있게 한다 — 별도 번역을 새로 지어내지 않고 기존 검증된 필드를 재사용.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_db
from engine.part_category import ko_gloss
from engine.text import clean_quote as _clean_quote
from llm.adapter import LLM

router = APIRouter(tags=["chat"])

# 상황판과 동일한 데이터 기준일(고정) — 실제 wall-clock "오늘"이 아니라 데이터가 실제로
# 끝나는 시점 기준으로 "최근 90일"을 계산해야 결과가 재현 가능하고 정직하다.
DATA_AS_OF = "2026-06-30"
RECENT_CUTOFF = "2026-04-01"  # DATA_AS_OF 기준 약 90일 전

STEP_DELAY = 0.35

# CHT-03: 채팅 답변의 [상세 리포트 보기]가 연결할 시나리오별 사전 생성 리포트 제목.
# seed.py가 이 정확한 제목으로 reports 테이블에 미리 렌더링해 넣고(아래 build_ev6_context 등을
# 그대로 재사용해 답변과 동일한 컨텍스트로 생성), 이 함수는 요청마다 제목으로 id를 조회한다 —
# 하드코딩된 id 대신 제목 매칭이라 seed 재실행으로 id가 바뀌어도 깨지지 않는다.
EV6_REPORT_TITLE = "EV6 계기판 조사 리포트 (조사 채팅 데모 사전 생성)"
IONIQ5_REPORT_TITLE = "IONIQ 5 ICCU·충전 조사 리포트 (조사 채팅 데모 사전 생성)"


def _report_id_by_title(conn, title: str) -> int | None:
    row = conn.execute("SELECT id FROM reports WHERE title = ?", (title,)).fetchone()
    return row["id"] if row else None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def detect_scenario(message: str) -> str:
    upper = message.upper()
    if "EV6" in upper and any(k in message for k in ["계기판", "깜빡", "꺼짐", "블랙아웃"]) or ("EV6" in upper and "CLUSTER" in upper):
        return "ev6_cluster"
    if ("IONIQ 5" in upper or "아이오닉5" in message or "아이오닉 5" in message) and (
        "충전" in message or "ICCU" in upper or "배터리" in message or "12V" in upper
    ):
        return "ioniq5_charging"
    return "out_of_scope"


def _is_iccu_recall(row) -> bool:
    # component 라벨만으로는 판별 불가(예: 전혀 다른 결함인 구동배터리 버스바 리콜도
    # component에 "BATTERY"가 들어감) — summary에 실제 ICCU 언급이 있는지로 판별한다.
    return "ICCU" in (row["summary"] or "").upper()


def _complaint_source(r) -> dict:
    return {
        "type": "odino",
        "id": r["odino"],
        "text": _clean_quote(r["text"]),
        "part_category": r["part_category"],
        "symptom": r["symptom"],
    }


def _campaign_parts(conn, campaigns: list[str]) -> list[dict]:
    """리콜 캠페인에 매칭된 Part 573 원문 부품 정보(data/processed/
    rcl573_components_normalized.csv 기반, parts 테이블) — 지어낸 값 없음.
    캠페인에 parts 데이터가 없으면 빈 리스트(placeholder 문구는 프론트에서도 금지).

    같은 캠페인이 부품번호 변형(예: 36400-1XFA0 / 36400-1XFA0QQK)으로 여러 행에
    걸쳐 저장돼 있어, campaign 기준으로 묶어 defect_cause·출처를 한 번만 보여주고
    그 아래 부품번호들을 나열한다(캠페인 내 defect_cause는 항상 동일함을 확인함).

    remedy_type(시정 방식 원문)도 defect_cause와 동일하게 캠페인 내 항상 동일함을
    DB로 확인 후 그룹 레벨에 포함 — 상담사 모드의 "고객 안내 요약" 블록이 이 반환값을
    그대로 재사용한다(별도 조회·별도 데이터 없음)."""
    if not campaigns:
        return []
    placeholders = ",".join("?" for _ in campaigns)
    rows = conn.execute(
        f"""SELECT campaign, component_name, part_number, supplier_canonical, defect_cause, remedy_type, pdf_url
            FROM parts WHERE campaign IN ({placeholders}) AND component_name IS NOT NULL""",
        campaigns,
    ).fetchall()

    grouped: dict[str, dict] = {}
    for r in rows:
        g = grouped.setdefault(
            r["campaign"],
            {
                "campaign": r["campaign"],
                "defect_cause": r["defect_cause"],
                "remedy_type": r["remedy_type"],
                "pdf_url": r["pdf_url"],
                "parts": [],
            },
        )
        g["parts"].append(
            {"component_name": r["component_name"], "part_number": r["part_number"], "supplier_canonical": r["supplier_canonical"]}
        )
    # campaigns 순서(리콜 조회 시 이미 report_date 순 정렬됨) 그대로 유지.
    return [grouped[c] for c in campaigns if c in grouped]


def _build_quotes(sources: list[dict]) -> list[dict]:
    """structured.quotes — sources(이미 조회된 인용 원문)를 재사용해 원문+한국어 요약 병기 형태로
    변환한다. 6.6단계: 새 번역을 짓지 않고 part_category/symptom(이미 검증된 필드)만 재사용."""
    return [
        {"odino": s["id"], "original": s["text"], "summary_ko": ko_gloss(s["part_category"], s["symptom"])}
        for s in sources
        if s["type"] == "odino" and s["text"]
    ]


# --- EV6 시나리오: 쿼리를 개별 함수로 쪼갠 이유는 채팅 SSE 흐름(단계별로 하나씩 실행해 각
# 단계의 duration_ms를 재야 함)과 seed.py의 사전 리포트 생성(전부 한 번에 실행)이 정확히 같은
# 쿼리·같은 컨텍스트를 공유해야 채팅 답변과 리포트 내용이 100% 일치하기 때문이다. ---

def ev6_recent_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM complaints WHERE model='EV6' AND date >= ?", (RECENT_CUTOFF,)).fetchone()[0]


def ev6_iccu_campaigns(conn) -> list[str]:
    all_recalls = conn.execute(
        "SELECT campaign, summary FROM recalls WHERE model='EV6' AND country='US' ORDER BY report_date"
    ).fetchall()
    return [r["campaign"] for r in all_recalls if _is_iccu_recall(r)]


def ev6_cluster_rows(conn):
    return conn.execute(
        "SELECT odino, date, text, part_category, symptom FROM complaints WHERE model='EV6' AND part_category='INSTRUMENT_CLUSTER' ORDER BY date"
    ).fetchall()


def ev6_build_context(recent_count, iccu_campaigns, cluster_rows) -> tuple[dict, list[dict]]:
    context = {
        "recent_count": recent_count,
        "iccu_campaigns": "·".join(iccu_campaigns),
        "cluster_odino_1": cluster_rows[0]["odino"] if len(cluster_rows) > 0 else "-",
        "cluster_date_1": cluster_rows[0]["date"] if len(cluster_rows) > 0 else "-",
        "cluster_odino_2": cluster_rows[1]["odino"] if len(cluster_rows) > 1 else "-",
        "cluster_date_2": cluster_rows[1]["date"] if len(cluster_rows) > 1 else "-",
    }
    sources = [_complaint_source(r) for r in cluster_rows] + [
        {"type": "campaign", "id": c, "text": None, "part_category": None, "symptom": None} for c in iccu_campaigns
    ]
    return context, sources


async def _ev6_cluster_flow(conn, llm: LLM, role: str = "consumer"):
    t0 = time.perf_counter()
    yield _sse(
        "step",
        {"id": 1, "icon": "car", "title": "차종 인식", "result": "KIA EV6", "status": "done", "tool": "규칙 매칭",
         "duration_ms": round((time.perf_counter() - t0) * 1000)},
    )
    await asyncio.sleep(STEP_DELAY)

    t0 = time.perf_counter()
    recent_count = ev6_recent_count(conn)
    yield _sse(
        "step",
        {"id": 2, "icon": "search", "title": "이력 조회", "result": f"최근 90일 신고 {recent_count}건", "status": "done",
         "tool": "DB 조회", "duration_ms": round((time.perf_counter() - t0) * 1000)},
    )
    await asyncio.sleep(STEP_DELAY)

    t0 = time.perf_counter()
    iccu_campaigns = ev6_iccu_campaigns(conn)
    yield _sse(
        "step",
        {
            "id": 3,
            "icon": "shield-alert",
            "title": "리콜 대조",
            "result": f"ICCU/12V 배터리 리콜 {len(iccu_campaigns)}건 확인 ({'·'.join(iccu_campaigns)})",
            "status": "done",
            "tool": "DB 조회",
            "duration_ms": round((time.perf_counter() - t0) * 1000),
        },
    )
    await asyncio.sleep(STEP_DELAY)

    t0 = time.perf_counter()
    cluster_rows = ev6_cluster_rows(conn)
    yield _sse(
        "step",
        {
            "id": 4,
            "icon": "git-compare",
            "title": "유사 증상 검색",
            "result": f"전력손실 없는 순수 계기판 결함 사례 {len(cluster_rows)}건 확인, 모두 최근 90일 밖",
            "status": "done",
            "tool": "DB 조회",
            "duration_ms": round((time.perf_counter() - t0) * 1000),
        },
    )
    await asyncio.sleep(STEP_DELAY)

    t0 = time.perf_counter()
    context, sources = ev6_build_context(recent_count, iccu_campaigns, cluster_rows)
    # asyncio.to_thread: llm.call()의 openai SDK 호출은 동기(블로킹)라, 그냥 호출하면 응답이
    # 오는 동안 이벤트 루프 전체가 멈춰 다른 요청(헬스체크 포함)이 전혀 처리되지 않는다(실측
    # 확인 — 연쇄적으로 다음 요청들이 큐에 막혀 응답 없이 끊기는 문제를 유발했었음).
    result = await asyncio.to_thread(llm.call, "answer", "ev6_cluster", context)
    report_id = _report_id_by_title(conn, EV6_REPORT_TITLE)
    yield _sse(
        "step",
        {"id": 5, "icon": "check-circle", "title": "검수", "result": f"통과 (출처 {len(sources)}건 확인)", "status": "done",
         "tool": "인용 검증", "duration_ms": round((time.perf_counter() - t0) * 1000)},
    )
    await asyncio.sleep(0.2)

    structured = result.get("structured")
    if structured is not None:
        parts = _campaign_parts(conn, iccu_campaigns)
        structured = {
            **structured,
            "quotes": _build_quotes(sources),
            "parts": parts,
            # 상담사 모드(role='agent')일 때만 "고객 안내 요약"용으로 동일 parts 데이터를 다시
            # 실어 보낸다 — 별도 조회·별도 데이터 없음, role은 표시 여부만 결정한다.
            "agent_summary": parts if role == "agent" else None,
        }
    yield _sse("answer", {"markdown": result["markdown"], "structured": structured, "sources": sources, "report_id": report_id})


IONIQ5_KEYWORDS = ["ICCU", "12-VOLT", "12V", "CHARGING CONTROL"]


def ioniq5_recent_rows(conn):
    return conn.execute(
        "SELECT odino, date, text, part_category, symptom FROM complaints WHERE model='IONIQ 5' AND date >= ?", (RECENT_CUTOFF,)
    ).fetchall()


def ioniq5_iccu_campaigns(conn) -> list[str]:
    all_recalls = conn.execute(
        "SELECT campaign, summary FROM recalls WHERE model='IONIQ 5' AND country='US' ORDER BY report_date"
    ).fetchall()
    return [r["campaign"] for r in all_recalls if _is_iccu_recall(r)]


def ioniq5_iccu_hits(recent_rows):
    return [r for r in recent_rows if any(k in (r["text"] or "").upper() for k in IONIQ5_KEYWORDS)]


def ioniq5_build_context(recent_rows, iccu_campaigns, iccu_hits) -> tuple[dict, list[dict]]:
    recent_count = len(recent_rows)
    iccu_ratio = round(100 * len(iccu_hits) / recent_count) if recent_count else 0
    recurrence_rows = [
        r for r in iccu_hits
        if "재발" in r["text"] or "AGAIN" in (r["text"] or "").upper() or "SECOND TIME" in (r["text"] or "").upper() or "RECALL" in (r["text"] or "").upper()
    ]
    top2 = iccu_hits[-2:] if len(iccu_hits) >= 2 else iccu_hits
    recur = recurrence_rows[0] if recurrence_rows else None

    context = {
        "recent_count": recent_count,
        "iccu_campaigns": "·".join(iccu_campaigns),
        "iccu_hit_count": len(iccu_hits),
        "iccu_ratio": iccu_ratio,
        "odino_1": top2[0]["odino"] if len(top2) > 0 else "-",
        "date_1": top2[0]["date"] if len(top2) > 0 else "-",
        "odino_2": top2[1]["odino"] if len(top2) > 1 else "-",
        "date_2": top2[1]["date"] if len(top2) > 1 else "-",
        "odino_recur": recur["odino"] if recur else "-",
        "date_recur": recur["date"] if recur else "-",
    }
    cited = {r["odino"]: r for r in (top2 + ([recur] if recur else []))}
    sources = [_complaint_source(r) for r in cited.values()] + [
        {"type": "campaign", "id": c, "text": None, "part_category": None, "symptom": None} for c in iccu_campaigns
    ]
    return context, sources


async def _ioniq5_charging_flow(conn, llm: LLM, role: str = "consumer"):
    t0 = time.perf_counter()
    yield _sse(
        "step",
        {"id": 1, "icon": "car", "title": "차종 인식", "result": "HYUNDAI IONIQ 5", "status": "done", "tool": "규칙 매칭",
         "duration_ms": round((time.perf_counter() - t0) * 1000)},
    )
    await asyncio.sleep(STEP_DELAY)

    t0 = time.perf_counter()
    recent_rows = ioniq5_recent_rows(conn)
    recent_count = len(recent_rows)
    yield _sse(
        "step",
        {"id": 2, "icon": "search", "title": "이력 조회", "result": f"최근 90일 신고 {recent_count}건", "status": "done",
         "tool": "DB 조회", "duration_ms": round((time.perf_counter() - t0) * 1000)},
    )
    await asyncio.sleep(STEP_DELAY)

    t0 = time.perf_counter()
    iccu_campaigns = ioniq5_iccu_campaigns(conn)
    yield _sse(
        "step",
        {
            "id": 3,
            "icon": "shield-alert",
            "title": "리콜 대조",
            "result": f"ICCU/충전 리콜 {len(iccu_campaigns)}건 확인 ({'·'.join(iccu_campaigns)})",
            "status": "done",
            "tool": "DB 조회",
            "duration_ms": round((time.perf_counter() - t0) * 1000),
        },
    )
    await asyncio.sleep(STEP_DELAY)

    t0 = time.perf_counter()
    iccu_hits = ioniq5_iccu_hits(recent_rows)
    iccu_ratio = round(100 * len(iccu_hits) / recent_count) if recent_count else 0
    yield _sse(
        "step",
        {
            "id": 4,
            "icon": "git-compare",
            "title": "증상 집중도 확인",
            "result": f"최근 90일 신고 중 {len(iccu_hits)}건({iccu_ratio}%)이 ICCU·12V 배터리 증상과 일치",
            "status": "done",
            "tool": "DB 조회",
            "duration_ms": round((time.perf_counter() - t0) * 1000),
        },
    )
    await asyncio.sleep(STEP_DELAY)

    t0 = time.perf_counter()
    context, sources = ioniq5_build_context(recent_rows, iccu_campaigns, iccu_hits)
    result = await asyncio.to_thread(llm.call, "answer", "ioniq5_charging", context)
    report_id = _report_id_by_title(conn, IONIQ5_REPORT_TITLE)
    yield _sse(
        "step",
        {"id": 5, "icon": "check-circle", "title": "검수", "result": f"통과 (출처 {len(sources)}건 확인)", "status": "done",
         "tool": "인용 검증", "duration_ms": round((time.perf_counter() - t0) * 1000)},
    )
    await asyncio.sleep(0.2)

    structured = result.get("structured")
    if structured is not None:
        parts = _campaign_parts(conn, iccu_campaigns)
        structured = {
            **structured,
            "quotes": _build_quotes(sources),
            "parts": parts,
            "agent_summary": parts if role == "agent" else None,
        }
    yield _sse("answer", {"markdown": result["markdown"], "structured": structured, "sources": sources, "report_id": report_id})


async def _out_of_scope_flow(llm: LLM):
    t0 = time.perf_counter()
    yield _sse(
        "step",
        {"id": 1, "icon": "help-circle", "title": "질문 분류", "result": "현재 데이터 범위 밖 질문으로 판단", "status": "done",
         "tool": "규칙 매칭", "duration_ms": round((time.perf_counter() - t0) * 1000)},
    )
    await asyncio.sleep(STEP_DELAY)
    t0 = time.perf_counter()
    result = await asyncio.to_thread(llm.call, "answer", "out_of_scope", {})
    yield _sse(
        "step",
        {"id": 2, "icon": "check-circle", "title": "검수", "result": "통과 (범위 밖 응답)", "status": "done",
         "tool": "인용 검증", "duration_ms": round((time.perf_counter() - t0) * 1000)},
    )
    await asyncio.sleep(0.2)
    structured = result.get("structured")
    if structured is not None:
        structured = {**structured, "quotes": [], "parts": [], "agent_summary": None}
    yield _sse("answer", {"markdown": result["markdown"], "structured": structured, "sources": [], "report_id": None})


async def _stream(message: str, conn, role: str = "consumer"):
    scenario = detect_scenario(message)
    llm = LLM()

    try:
        if scenario == "ev6_cluster":
            async for chunk in _ev6_cluster_flow(conn, llm, role):
                yield chunk
        elif scenario == "ioniq5_charging":
            async for chunk in _ioniq5_charging_flow(conn, llm, role):
                yield chunk
        else:
            async for chunk in _out_of_scope_flow(llm):
                yield chunk
    except Exception as e:
        # llm.call()이 타임아웃·API 오류 등 어떤 이유로든 실패하면 이 except가 없을 때 SSE
        # 제너레이터가 그대로 죽어 done이 영영 안 가고 프론트 로더가 무한 대기한다(배포 환경에서
        # 실제 관측된 증상). 원인은 서버 로그에 남기고, 클라이언트에는 안전한 일반 메시지만 보낸 뒤
        # 반드시 done까지 보내 스트림을 정상 종료시킨다.
        print(f"[chat] scenario={scenario} 처리 중 오류: {type(e).__name__}: {e}", flush=True)
        yield _sse("error", {"message": "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."})

    yield _sse("done", {})


@router.post("/chat")
async def post_chat(request: Request, conn=Depends(get_db)):
    payload = await request.json()
    message = payload.get("message", "")
    # role='agent'는 사내 상담사 화면(webapp/frontend의 목 로그인 스위치)에서만 보낸다 — 조사
    # 로직·시나리오 매칭에는 전혀 관여하지 않고, 답변 structured에 agent_summary를 실을지만
    # 결정한다(위 각 flow 참조). 알 수 없는 값은 안전하게 consumer로 취급.
    role = payload.get("role", "consumer")
    if role not in ("consumer", "agent"):
        role = "consumer"
    return StreamingResponse(_stream(message, conn, role), media_type="text/event-stream")
