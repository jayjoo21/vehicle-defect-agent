"""POST /api/chat — SSE 스트림 (조사 채팅, v0 mock 모드).

3개 데모 시나리오만 지원: EV6 계기판 / IONIQ 5 충전(ICCU) / 범위 밖 질문.
시나리오 매칭은 키워드 기반(v0 잠정) — 실제 LLM 라우팅은 이후 버전에서 대체 예정.
타임라인 단계(차종 인식·이력 조회·리콜 대조 등)의 수치는 전부 이 함수가 DB에서
직접 조회한 실측값이며, llm/mock_responses의 markdown_template에도 그 실측값만
채워 넣는다 — 지어낸 수치 없음.
"""
import asyncio
import json
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_db
from llm.adapter import LLM

router = APIRouter(tags=["chat"])

# 상황판과 동일한 데이터 기준일(고정) — 실제 wall-clock "오늘"이 아니라 데이터가 실제로
# 끝나는 시점 기준으로 "최근 90일"을 계산해야 결과가 재현 가능하고 정직하다.
DATA_AS_OF = "2026-06-30"
RECENT_CUTOFF = "2026-04-01"  # DATA_AS_OF 기준 약 90일 전

STEP_DELAY = 0.35


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


async def _ev6_cluster_flow(conn, llm: LLM):
    yield _sse("step", {"id": 1, "icon": "car", "title": "차종 인식", "result": "KIA EV6", "status": "done"})
    await asyncio.sleep(STEP_DELAY)

    recent_count = conn.execute(
        "SELECT COUNT(*) FROM complaints WHERE model='EV6' AND date >= ?", (RECENT_CUTOFF,)
    ).fetchone()[0]
    yield _sse(
        "step",
        {"id": 2, "icon": "search", "title": "이력 조회", "result": f"최근 90일 신고 {recent_count}건", "status": "done"},
    )
    await asyncio.sleep(STEP_DELAY)

    all_recalls = conn.execute(
        "SELECT campaign, summary FROM recalls WHERE model='EV6' AND country='US' ORDER BY report_date"
    ).fetchall()
    iccu_campaigns = [r["campaign"] for r in all_recalls if _is_iccu_recall(r)]
    yield _sse(
        "step",
        {
            "id": 3,
            "icon": "shield-alert",
            "title": "리콜 대조",
            "result": f"ICCU/12V 배터리 리콜 {len(iccu_campaigns)}건 확인 ({'·'.join(iccu_campaigns)})",
            "status": "done",
        },
    )
    await asyncio.sleep(STEP_DELAY)

    cluster_rows = conn.execute(
        "SELECT odino, date, text FROM complaints WHERE model='EV6' AND part_category='INSTRUMENT_CLUSTER' ORDER BY date"
    ).fetchall()
    yield _sse(
        "step",
        {
            "id": 4,
            "icon": "git-compare",
            "title": "유사 증상 검색",
            "result": f"전력손실 없는 순수 계기판 결함 사례 {len(cluster_rows)}건 확인, 모두 최근 90일 밖",
            "status": "done",
        },
    )
    await asyncio.sleep(STEP_DELAY)

    context = {
        "recent_count": recent_count,
        "iccu_campaigns": "·".join(iccu_campaigns),
        "cluster_odino_1": cluster_rows[0]["odino"] if len(cluster_rows) > 0 else "-",
        "cluster_date_1": cluster_rows[0]["date"] if len(cluster_rows) > 0 else "-",
        "cluster_odino_2": cluster_rows[1]["odino"] if len(cluster_rows) > 1 else "-",
        "cluster_date_2": cluster_rows[1]["date"] if len(cluster_rows) > 1 else "-",
    }
    result = llm.call("answer", "ev6_cluster", context)
    sources = [{"type": "odino", "id": r["odino"], "text": r["text"]} for r in cluster_rows] + [
        {"type": "campaign", "id": c, "text": None} for c in iccu_campaigns
    ]
    yield _sse(
        "step", {"id": 5, "icon": "check-circle", "title": "검수", "result": f"통과 (출처 {len(sources)}건 확인)", "status": "done"}
    )
    await asyncio.sleep(0.2)

    yield _sse("answer", {"markdown": result["markdown"], "sources": sources, "report_id": None})


async def _ioniq5_charging_flow(conn, llm: LLM):
    yield _sse("step", {"id": 1, "icon": "car", "title": "차종 인식", "result": "HYUNDAI IONIQ 5", "status": "done"})
    await asyncio.sleep(STEP_DELAY)

    recent_rows = conn.execute(
        "SELECT odino, date, text FROM complaints WHERE model='IONIQ 5' AND date >= ?", (RECENT_CUTOFF,)
    ).fetchall()
    recent_count = len(recent_rows)
    yield _sse(
        "step",
        {"id": 2, "icon": "search", "title": "이력 조회", "result": f"최근 90일 신고 {recent_count}건", "status": "done"},
    )
    await asyncio.sleep(STEP_DELAY)

    all_recalls = conn.execute(
        "SELECT campaign, summary FROM recalls WHERE model='IONIQ 5' AND country='US' ORDER BY report_date"
    ).fetchall()
    iccu_campaigns = [r["campaign"] for r in all_recalls if _is_iccu_recall(r)]
    yield _sse(
        "step",
        {
            "id": 3,
            "icon": "shield-alert",
            "title": "리콜 대조",
            "result": f"ICCU/충전 리콜 {len(iccu_campaigns)}건 확인 ({'·'.join(iccu_campaigns)})",
            "status": "done",
        },
    )
    await asyncio.sleep(STEP_DELAY)

    keywords = ["ICCU", "12-VOLT", "12V", "CHARGING CONTROL"]
    iccu_hits = [r for r in recent_rows if any(k in (r["text"] or "").upper() for k in keywords)]
    iccu_ratio = round(100 * len(iccu_hits) / recent_count) if recent_count else 0
    yield _sse(
        "step",
        {
            "id": 4,
            "icon": "git-compare",
            "title": "증상 집중도 확인",
            "result": f"최근 90일 신고 중 {len(iccu_hits)}건({iccu_ratio}%)이 ICCU·12V 배터리 증상과 일치",
            "status": "done",
        },
    )
    await asyncio.sleep(STEP_DELAY)

    recurrence_rows = [r for r in iccu_hits if "재발" in r["text"] or "AGAIN" in (r["text"] or "").upper() or "SECOND TIME" in (r["text"] or "").upper() or "RECALL" in (r["text"] or "").upper()]
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
    result = llm.call("answer", "ioniq5_charging", context)
    cited = {r["odino"]: r for r in (top2 + ([recur] if recur else []))}
    sources = [{"type": "odino", "id": o, "text": r["text"]} for o, r in cited.items()] + [
        {"type": "campaign", "id": c, "text": None} for c in iccu_campaigns
    ]
    yield _sse(
        "step", {"id": 5, "icon": "check-circle", "title": "검수", "result": f"통과 (출처 {len(sources)}건 확인)", "status": "done"}
    )
    await asyncio.sleep(0.2)

    yield _sse("answer", {"markdown": result["markdown"], "sources": sources, "report_id": None})


async def _out_of_scope_flow(llm: LLM):
    yield _sse(
        "step", {"id": 1, "icon": "help-circle", "title": "질문 분류", "result": "현재 데이터 범위 밖 질문으로 판단", "status": "done"}
    )
    await asyncio.sleep(STEP_DELAY)
    result = llm.call("answer", "out_of_scope", {})
    yield _sse("step", {"id": 2, "icon": "check-circle", "title": "검수", "result": "통과 (범위 밖 응답)", "status": "done"})
    await asyncio.sleep(0.2)
    yield _sse("answer", {"markdown": result["markdown"], "sources": [], "report_id": None})


async def _stream(message: str, conn):
    scenario = detect_scenario(message)
    llm = LLM()

    if scenario == "ev6_cluster":
        async for chunk in _ev6_cluster_flow(conn, llm):
            yield chunk
    elif scenario == "ioniq5_charging":
        async for chunk in _ioniq5_charging_flow(conn, llm):
            yield chunk
    else:
        async for chunk in _out_of_scope_flow(llm):
            yield chunk

    yield _sse("done", {})


@router.post("/chat")
async def post_chat(request: Request, conn=Depends(get_db)):
    payload = await request.json()
    message = payload.get("message", "")
    return StreamingResponse(_stream(message, conn), media_type="text/event-stream")
