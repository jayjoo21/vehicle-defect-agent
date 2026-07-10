#!/usr/bin/env python3
"""
str01_batch_structurize.py — 신고 CSV 일괄 구조화 (STR-01 + STR-02 인용 검사 내장)

과정: 검증된 프롬프트 v2(docs/struct_prompt_v2.md)로 CDESCR를 LLM API 일괄 구조화.
입력: 신고 CSV (ODINO, CDESCR 컬럼 필수)
출력: JSONL — 건당 {odino, part_category, symptoms, severity, driving_context,
      evidence_quote, insufficient_info}

건별 루프: 호출 → JSON 파싱 → 스키마 검사 → 인용 verbatim 검사(struct_verify.py와
동일 로직) → 실패 시 오류 사유를 프롬프트에 덧붙여 재시도(최대 3회) → 통과 건만
즉시 append 저장(중단 후 재실행 시 처리된 ODINO는 건너뜀 = 이어하기).

LLM 제공사는 PROVIDER 환경변수로 교체 가능(gemini | anthropic). 표준 라이브러리만
사용(새 의존성 없음 — CLAUDE.md 원칙).

사용:
  python scripts/str01_batch_structurize.py                 # 기본 100건 파일
  python scripts/str01_batch_structurize.py --limit 5       # 시운전
  python scripts/str01_batch_structurize.py --input data/processed/hk_electrical_recent_full.csv
"""
import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = REPO_ROOT / "docs" / "struct_prompt_v2.md"
DEFAULT_INPUT = REPO_ROOT / "data" / "samples" / "sample_100_for_meeting.csv"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "processed" / "str01_sample100_results.jsonl"
FAILURES_SUFFIX = "_failures.jsonl"

MAX_ATTEMPTS = 3          # 검증 실패 시 건당 최대 시도 횟수
RATE_LIMIT_WAITS = [15, 30, 60, 120]  # 429/503 백오프(초)

# ── 스키마 정의 (struct_verify.py와 동일) ───────────────────────────
ALLOWED_PARTS = {
    "ELECTRICAL_SYSTEM", "ADAS", "INSTRUMENT_CLUSTER", "PROPULSION_BATTERY",
    "BRAKES_ELECTRONIC", "POWERTRAIN_SW", "NON_ELECTRICAL", "INSUFFICIENT_INFO",
}
ALLOWED_SEVERITY = {"CRITICAL", "SERIOUS", "MODERATE", "MINOR"}
REQUIRED_KEYS = {"odino", "part_category", "symptoms", "severity",
                 "driving_context", "evidence_quote", "insufficient_info"}


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


# ── LLM 호출 (provider 교체 지점) ────────────────────────────────────
def call_llm(prompt: str, env: dict) -> str:
    provider = env.get("PROVIDER", "gemini")
    if provider == "gemini":
        return _call_gemini(prompt, env)
    if provider == "anthropic":
        return _call_anthropic(prompt, env)
    raise ValueError(f"지원하지 않는 PROVIDER: {provider}")


def _post_json(url: str, body: dict, headers: dict) -> dict:
    """공통 HTTP POST — 429/503은 백오프 후 재시도."""
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


def _call_gemini(prompt: str, env: dict) -> str:
    model = env.get("GEMINI_MODEL", "gemini-3.5-flash")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={env['GEMINI_API_KEY']}")
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    resp = _post_json(url, body, {})
    return resp["candidates"][0]["content"]["parts"][0]["text"]


def _call_anthropic(prompt: str, env: dict) -> str:
    model = env.get("ANTHROPIC_MODEL", "claude-sonnet-5")
    body = {
        "model": model,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {"x-api-key": env["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"}
    resp = _post_json("https://api.anthropic.com/v1/messages", body, headers)
    return next(b["text"] for b in resp["content"] if b["type"] == "text")


# ── 검증 (struct_verify.py와 동일 로직) ─────────────────────────────
def fix_mojibake(text: str) -> str:
    """원본 CSV의 UTF-8→latin-1 오디코딩(모지바케) 복구.
    예: 'couldnâ\\x80\\x99t' → "couldn't". 복구 불가 시 원문 그대로."""
    if not isinstance(text, str):
        return ""
    if "â" in text or "Ã" in text:  # 전형적 모지바케 시그니처
        try:
            return text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text
    return text


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


def check_schema(rec):
    errors = []
    missing = REQUIRED_KEYS - rec.keys()
    if missing:
        errors.append(f"누락 키: {sorted(missing)}")
    if rec.get("part_category") not in ALLOWED_PARTS:
        errors.append(f"part_category 허용값 위반: {rec.get('part_category')!r}")
    if rec.get("severity") not in ALLOWED_SEVERITY:
        errors.append(f"severity 허용값 위반: {rec.get('severity')!r}")
    if not isinstance(rec.get("symptoms"), list):
        errors.append("symptoms가 list가 아님")
    if not isinstance(rec.get("insufficient_info"), bool):
        errors.append(f"insufficient_info가 bool이 아님: {rec.get('insufficient_info')!r}")
    return errors


def check_quote(quote: str, cdescr: str) -> bool:
    q_norm, c_norm = normalize_text(quote), normalize_text(cdescr)
    if q_norm and q_norm in c_norm:
        return True
    if len(q_norm) >= 20:
        return q_norm[:20] in c_norm
    return False


# ── 건별 구조화 ──────────────────────────────────────────────────────
def structurize_one(odino, cdescr, base_prompt, env):
    """반환: (통과 레코드 | None, 통계 {attempts, errors})"""
    stats = {"attempts": 0, "errors": []}
    feedback = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        stats["attempts"] = attempt
        prompt = (f"{base_prompt}\n\n---\n\n**입력:**\nODINO: {odino}\nCDESCR: {cdescr}"
                  + feedback)
        raw = call_llm(prompt, env)
        # JSON 파싱 (마크다운 펜스 방어)
        raw_clean = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        try:
            rec = json.loads(raw_clean)
        except json.JSONDecodeError as e:
            stats["errors"].append(f"시도{attempt}: JSON 파싱 실패 ({e})")
            feedback = "\n\n[재시도 지시] 직전 응답이 유효한 JSON이 아니었다. 코드펜스·설명 없이 JSON 객체 하나만 출력하라."
            continue
        rec["odino"] = str(rec.get("odino", odino)) or odino
        # 스키마 허용값에 괄호 설명이 붙어 있어 LLM이 통째로 복사하는 경우 정규화
        # 예: 'ADAS(전방충돌·차선·후방카메라 등 운전보조)' → 'ADAS'
        pc = rec.get("part_category")
        if isinstance(pc, str) and "(" in pc:
            rec["part_category"] = pc.split("(")[0].strip()
        errs = check_schema(rec)
        if not check_quote(rec.get("evidence_quote", ""), cdescr):
            errs.append("evidence_quote가 원문에 없음(환각)")
        if not errs:
            return rec, stats
        stats["errors"].append(f"시도{attempt}: {'; '.join(errs)}")
        feedback = ("\n\n[재시도 지시] 직전 응답이 다음 검증에 실패했다. 스키마의 허용값을 정확히 지키고, "
                    "evidence_quote는 반드시 CDESCR 원문에서 한 글자도 바꾸지 말고 그대로 복사하라. "
                    f"실패 사유: {'; '.join(errs)}")
    return None, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(DEFAULT_INPUT))
    ap.add_argument("--output", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--limit", type=int, default=0, help="앞 N건만 처리(시운전용)")
    args = ap.parse_args()

    env = load_env()
    base_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    out_path = Path(args.output)
    fail_path = out_path.with_name(out_path.stem + FAILURES_SUFFIX)

    # 입력 로드
    with open(args.input, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f)]
    if args.limit:
        rows = rows[: args.limit]

    # 이어하기: 기존 출력의 ODINO 스킵
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(str(json.loads(line)["odino"]))

    todo = [r for r in rows if str(r["ODINO"]) not in done]
    print(f"입력 {len(rows)}건 / 기존 처리 {len(rows) - len(todo)}건 / 이번 처리 {len(todo)}건")
    print(f"PROVIDER={env.get('PROVIDER', 'gemini')}, MODEL={env.get('GEMINI_MODEL', 'gemini-3.5-flash')}\n")

    n_ok, n_fail, n_retried, t0 = 0, 0, 0, time.time()
    with open(out_path, "a", encoding="utf-8") as fout, \
         open(fail_path, "a", encoding="utf-8") as ffail:
        for i, row in enumerate(todo, 1):
            odino = str(row["ODINO"])
            cdescr = fix_mojibake(str(row["CDESCR"]))
            rec, stats = structurize_one(odino, cdescr, base_prompt, env)
            if rec:
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fout.flush()
                n_ok += 1
                if stats["attempts"] > 1:
                    n_retried += 1
                flag = f" (재시도 {stats['attempts'] - 1}회)" if stats["attempts"] > 1 else ""
                print(f"  [{i}/{len(todo)}] {odino} OK — {rec['part_category']}/{rec['severity']}{flag}")
            else:
                ffail.write(json.dumps({"odino": odino, "errors": stats["errors"]},
                                       ensure_ascii=False) + "\n")
                ffail.flush()
                n_fail += 1
                print(f"  [{i}/{len(todo)}] {odino} FAIL — {stats['errors'][-1]}")

    elapsed = time.time() - t0
    total_done = len(done) + n_ok
    print(f"\n=== STR-01 실행 요약 ===")
    print(f"  이번 실행: 성공 {n_ok} / 실패 {n_fail} (재시도 발생 {n_retried}건)")
    print(f"  누적 처리: {total_done}/{len(rows)}건")
    print(f"  소요: {elapsed:.0f}초")
    print(f"  출력: {out_path}")
    if n_fail:
        print(f"  실패 목록: {fail_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()
