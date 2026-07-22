#!/usr/bin/env python3
"""
rcl573_classify_compdesc.py — RCL573 리콜 레코드에 compdesc1(v4 7종) 분류 부여

배경 (설계 한계 C 돌파)
----------------------
sta01_02_status_tracking.py의 리콜 매칭(_component_matches)이 지금까지
COMPDESC1_RECALL_KEYWORDS라는 "문자열 겹침 키워드 사전"으로 리콜 component
텍스트와 STR의 compdesc1을 억지로 매칭해왔다. 이건 애초에 서로 다른 두 taxonomy
(NHTSA 소비자 신고 COMPDESC vs Part 573 리콜 신고서 자유 서술)를 키워드로
근사하는 거라 구조적으로 오탐/누락 여지가 있었다.

이 스크립트는 근본 해법이다 — STR이 소비자 신고 원문을 Gemini로 compdesc1
분류하듯, 리콜 레코드도 똑같은 방식으로 Gemini에게 같은 7종 카테고리로
분류시킨다. 이후 리콜 매칭은 키워드 추측이 아니라 compdesc1 == compdesc1
정확 비교로 바뀔 수 있다(후속 작업 — sta_recall_loader.py/
sta01_02_status_tracking.py 쪽 반영은 이 스크립트로 실제 분류 결과가 나온
뒤에 진행).

비용 설계 — "정확히 1번만" 원칙
--------------------------------
data/processed/rcl573_components_normalized.csv는 198행이지만, 같은 리콜
캠페인이 부품번호별로 여러 행에 걸쳐 반복되는 경우가 있어(실측: 33개 캠페인이
2행 이상) 실제 고유 캠페인은 76개뿐이다. 행 단위로 분류하면 같은 캠페인을
최대 몇 번씩 중복 분류해 API 비용을 낭비하게 되므로, 이 스크립트는 반드시
**캠페인 단위(76건)로만** Gemini를 호출하고, 그 결과를 캠페인이 같은 모든
행에 그대로 복사해 최종 198행 출력을 만든다.

추가 안전장치(전부 str01_batch_structurize.py와 동일한 관례):
1. 이어하기 — 출력 파일에 이미 있는 campaign은 재실행 시 건너뛴다. 중간에
   끊겨도(네트워크 오류, Ctrl+C 등) 재실행 시 이미 낸 비용이 중복되지 않는다.
2. --limit N — 전체 76건을 돌리기 전에 먼저 소량(예: 2~3건)으로 시운전해서
   프롬프트·스키마가 기대대로 동작하는지 확인할 수 있다.
3. --dry-run — 실제 API 호출 없이 "몇 건을 어떻게 처리할지"만 콘솔에 출력하고
   종료한다. 진짜 실행 전 최종 확인용.
4. 재시도는 건당 최대 3회로 제한(무한 재시도로 비용 새는 것 방지).

사용법
    # 1) 반드시 먼저 dry-run으로 몇 건이 어떻게 처리될지 확인
    python scripts/rcl573_classify_compdesc.py --dry-run

    # 2) 소량 시운전 (2건만 실제 호출 — 비용 거의 0)
    python scripts/rcl573_classify_compdesc.py --limit 2

    # 3) 시운전 결과 확인 후, 전체 76건 실행 (이미 처리된 2건은 자동 스킵)
    python scripts/rcl573_classify_compdesc.py

출력: data/processed/rcl573_components_with_compdesc1.csv
      (원본 198행 + compdesc1 컬럼 1개 추가. 원본 파일은 건드리지 않음)
"""
import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "data" / "processed" / "rcl573_components_normalized.csv"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "processed" / "rcl573_components_with_compdesc1.csv"

MAX_ATTEMPTS = 3
RATE_LIMIT_WAITS = [15, 30, 60, 120]

# STR v4와 완전히 동일한 7종 (str01_sample100_v4_results.jsonl 실물 확인 값,
# 공백 표기 — 언더스코어 아님). 여기서 값이 하나라도 다르면 이후 STA 쪽의
# 정확값 비교(compdesc1 == compdesc1)가 아예 안 맞게 되므로 절대 임의로
# 바꾸지 말 것.
ALLOWED_COMPDESC1 = {
    "ELECTRICAL SYSTEM",
    "UNKNOWN OR OTHER",
    "FORWARD COLLISION AVOIDANCE",
    "VEHICLE SPEED CONTROL",
    "LANE DEPARTURE",
    "BACK OVER PREVENTION",
    "ELECTRONIC STABILITY CONTROL (ESC)",
}

PROMPT_TEMPLATE = """너는 NHTSA(미국 도로교통안전국) 리콜 신고서(Part 573)의 결함 설명을 읽고,
아래 7개 부품 대분류(compdesc1) 중 정확히 하나로 분류하는 전문가다.

이 7개 분류는 NHTSA 소비자 신고 데이터의 COMPDESC 대분류와 동일한 체계다 —
리콜 텍스트가 자유 서술이라도, 그 결함이 "소비자 신고였다면 어느 COMPDESC로
분류됐을지"를 기준으로 판단하라.

# 분류 정의
- ELECTRICAL SYSTEM: 점화장치·경적·계기판/클러스터·배터리(12V/24V/48V)·
  알터네이터·배선·스타터·차체제어모듈(BCM)·소프트웨어 등 ADAS가 아닌 차량
  전반의 전기·전자 계통 결함.
- FORWARD COLLISION AVOIDANCE: 전방 충돌 회피 — 자동긴급제동(AEB), 전방충돌
  경고, 적응형 크루즈 컨트롤 관련 결함.
- VEHICLE SPEED CONTROL: 가속페달·크루즈컨트롤·스로틀 등 차량 속도가 운전자
  의도와 무관하게 제어되는 결함(의도치 않은 가속/감속 포함).
- LANE DEPARTURE: 차선이탈경고·차선유지보조·사각지대감지(BSD) 관련 결함.
- BACK OVER PREVENTION: 후진 시 후방 자동제동·후방카메라·후방 센싱 시스템
  관련 결함.
- ELECTRONIC STABILITY CONTROL (ESC): 전자식 차체자세제어장치(ESC) 관련
  결함(차량 자세 안정성 제어 모듈).
- UNKNOWN OR OTHER: 위 6개 중 어디에도 명확히 안 들어맞거나, 텍스트만으로는
  부위를 특정하기 어려운 경우. 억지로 끼워맞추지 말고 이 값을 써라.

# 입력
캠페인 번호: {campaign}
부품명: {component_name}
부품 설명: {component_desc}
결함 설명: {defect_cause}

# 출력 형식
아래 JSON 객체 하나만 출력하라(코드펜스·설명 금지):
{{"compdesc1": "위 7개 값 중 정확히 하나"}}"""


def load_env() -> dict:
    env = {}
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _post_json(url: str, body: dict, headers: dict) -> dict:
    data = json.dumps(body).encode()
    for i, wait in enumerate([0] + RATE_LIMIT_WAITS):
        if wait:
            print(f"    (rate limit — {wait}초 대기 후 재시도)")
            time.sleep(wait)
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and i < len(RATE_LIMIT_WAITS):
                continue
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:300]}")
    raise RuntimeError("rate limit 백오프 소진")


def call_gemini(prompt: str, env: dict) -> str:
    if "GEMINI_API_KEY" not in env:
        raise RuntimeError(
            "GEMINI_API_KEY가 .env에 없습니다. 레포 루트에 .env 파일을 만들고 "
            "GEMINI_API_KEY=발급받은키 한 줄을 넣어주세요(레포 관례 — 코드에 "
            "직접 키를 적지 않음, str01_batch_structurize.py와 동일)."
        )
    model = env.get("GEMINI_MODEL", "gemini-2.5-flash")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={env['GEMINI_API_KEY']}")
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    resp = _post_json(url, body, {})
    return resp["candidates"][0]["content"]["parts"][0]["text"]


def classify_one(campaign: str, component_name: str, component_desc: str,
                  defect_cause: str, env: dict) -> tuple[str | None, dict]:
    """반환: (compdesc1 또는 None, 통계 {attempts, errors})"""
    stats = {"attempts": 0, "errors": []}
    feedback = ""
    base_prompt = PROMPT_TEMPLATE.format(
        campaign=campaign,
        component_name=component_name or "(없음)",
        component_desc=component_desc or "(없음)",
        defect_cause=(defect_cause or "")[:1500],  # 결함 설명이 긴 경우 과금 절약을 위해 절단
    )
    for attempt in range(1, MAX_ATTEMPTS + 1):
        stats["attempts"] = attempt
        raw = call_gemini(base_prompt + feedback, env)
        raw_clean = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        try:
            rec = json.loads(raw_clean)
        except json.JSONDecodeError as e:
            stats["errors"].append(f"시도{attempt}: JSON 파싱 실패 ({e})")
            feedback = "\n\n[재시도 지시] 직전 응답이 유효한 JSON이 아니었다. JSON 객체 하나만 출력하라."
            continue
        value = rec.get("compdesc1")
        if value not in ALLOWED_COMPDESC1:
            stats["errors"].append(f"시도{attempt}: 허용값 아님 ({value!r})")
            feedback = (f"\n\n[재시도 지시] '{value}'는 허용된 7개 값에 없다. "
                        f"반드시 다음 중 정확히 하나만 써라: {sorted(ALLOWED_COMPDESC1)}")
            continue
        return value, stats
    return None, stats


def write_output(rows: list[dict], done: dict[str, str], out_path: Path) -> None:
    """현재 분류 상태를 원자적으로 저장해 중단 시에도 완료 결과를 보존한다."""
    fieldnames = list(rows[0].keys()) if rows else []
    if "compdesc1" not in fieldnames:
        fieldnames.append("compdesc1")
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out_row = dict(row)
            out_row["compdesc1"] = done.get((row.get("campaign") or "").strip(), "")
            writer.writerow(out_row)
    tmp_path.replace(out_path)


def main():
    ap = argparse.ArgumentParser(description="RCL573 리콜을 STR v4 compdesc1 7종으로 분류(캠페인 단위)")
    ap.add_argument("--input", default=str(DEFAULT_INPUT))
    ap.add_argument("--output", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--limit", type=int, default=0, help="앞 N개 캠페인만 처리(시운전용)")
    ap.add_argument("--dry-run", action="store_true", help="실제 API 호출 없이 처리 대상만 출력하고 종료")
    args = ap.parse_args()

    with open(args.input, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    # 캠페인 단위로 대표 행 하나만 골라서(첫 등장 행) 분류 입력으로 쓴다 —
    # 같은 캠페인의 여러 행은 보통 부품번호만 다르고 결함 설명(defect_cause)은
    # 동일하다(실측 확인).
    seen_campaigns = {}
    for r in rows:
        c = r.get("campaign", "").strip()
        if c and c not in seen_campaigns:
            seen_campaigns[c] = r
    unique_campaigns = list(seen_campaigns.items())
    print(f"입력 {len(rows)}행 / 고유 캠페인 {len(unique_campaigns)}개 "
          f"(캠페인 단위로만 분류하여 API 호출 {len(unique_campaigns)}회로 제한)")

    out_path = Path(args.output)
    # 이어하기: 기존 출력 파일에 이미 있는 campaign은 건너뛴다.
    done: dict[str, str] = {}
    if out_path.exists():
        with open(out_path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("compdesc1"):
                    done[r["campaign"]] = r["compdesc1"]
        print(f"기존 출력에서 이미 분류된 캠페인 {len(done)}개 발견 — 재실행 시 건너뜀(이어하기)")

    todo = [(c, r) for c, r in unique_campaigns if c not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"이번 실행 대상: {len(todo)}개 캠페인"
          + (f" (--limit {args.limit})" if args.limit else ""))

    if args.dry_run:
        print("\n[DRY RUN] 아래 캠페인들에 대해 Gemini API를 호출할 예정입니다(실제 호출 안 함):")
        for c, r in todo:
            print(f"  - {c}: {(r.get('defect_cause') or '')[:80]}...")
        print(f"\n총 {len(todo)}건. 진행하려면 --dry-run 없이 다시 실행하세요.")
        return

    if not todo:
        print("처리할 캠페인이 없습니다(전부 이어하기로 완료됨). --limit을 늘리거나 출력 파일을 확인하세요.")
    else:
        env = load_env()
        for i, (campaign, row) in enumerate(todo, 1):
            try:
                value, stats = classify_one(
                    campaign, row.get("component_name", ""), row.get("component_desc", ""),
                    row.get("defect_cause", ""), env,
                )
            except Exception as exc:
                print(f"  [{i}/{len(todo)}] {campaign} ERROR — {type(exc).__name__}: {exc}")
                continue
            if value:
                done[campaign] = value
                flag = f" (재시도 {stats['attempts']-1}회)" if stats["attempts"] > 1 else ""
                print(f"  [{i}/{len(todo)}] {campaign} -> {value}{flag}")
                write_output(rows, done, out_path)
            else:
                print(f"  [{i}/{len(todo)}] {campaign} FAIL — {stats['errors'][-1] if stats['errors'] else '알 수 없는 오류'}")

    write_output(rows, done, out_path)

    n_classified_rows = sum(1 for r in rows if done.get(r.get("campaign", "").strip()))
    print(f"\n저장 완료: {out_path}")
    print(f"전체 {len(rows)}행 중 compdesc1 채워진 행: {n_classified_rows}"
          f" / 분류된 고유 캠페인: {len(done)}/{len(unique_campaigns)}")
    if len(done) < len(unique_campaigns):
        print(f"-> 아직 {len(unique_campaigns) - len(done)}개 캠페인이 남았습니다. "
              f"같은 명령을 다시 실행하면 남은 것만 이어서 처리합니다(이미 낸 비용 중복 없음).")


if __name__ == "__main__":
    main()
