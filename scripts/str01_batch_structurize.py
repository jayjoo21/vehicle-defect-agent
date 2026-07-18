#!/usr/bin/env python3
"""
str01_batch_structurize.py — 신고 CSV 일괄 구조화 (STR-01 + STR-02 인용 검사 내장)

과정: 검증된 프롬프트로 CDESCR를 LLM API 일괄 구조화. --prompt로 v2/v3(ODINO 단위,
7~8필드)와 v4(CMPLID 단위, 9필드 — compdesc1/compdesc2는 코드가 채움) 둘 다 지원한다.
프롬프트 본문에 "compdesc1"이라는 문자열이 있으면 v4로 자동 인식한다.

v2/v3: 입력 ODINO/CDESCR → LLM이 odino/part_category 등 전부 판단.
v4: 입력 CMPLID/ODINO/COMPDESC/CDESCR → COMPDESC를 코드가 compdesc1/compdesc2로 잘라
    프롬프트 입력에 앵커로 넣어주고, compdesc1이 UNKNOWN OR OTHER일 때만 같은 ODINO의
    다른 행(형제) COMPDESC를 조회해 같이 넣어준다(형제 조회는 항상 원본 전체
    hk_electrical_recent_full.csv를 인덱스로 사용 — 부분표본을 처리할 때도 형제 유무가
    정확해야 하므로). LLM은 5필드(symptoms/severity/driving_context/evidence_quote/
    insufficient_info)만 판단하고, cmplid/odino/compdesc1/compdesc2는 코드가 채운다.

건별 루프: 호출 → JSON 파싱 → 스키마 검사 → 인용 verbatim 검사(struct_verify.py와
동일 로직, insufficient_info=true+빈 인용은 예외 허용) → 실패 시 오류 사유를 프롬프트에
덧붙여 재시도(최대 3회) → 통과 건만 즉시 append 저장(중단 후 재실행 시 처리된 건은
건너뜀 = 이어하기. 이어하기 키는 v2/v3는 odino, v4는 cmplid).

LLM 제공사는 PROVIDER 환경변수로 교체 가능(gemini | anthropic). 표준 라이브러리만
사용(새 의존성 없음 — CLAUDE.md 원칙).

사용:
  python scripts/str01_batch_structurize.py                 # 기본 100건 파일 (v2)
  python scripts/str01_batch_structurize.py --limit 5       # 시운전
  python scripts/str01_batch_structurize.py --input data/samples/sample_100_v4.csv \\
      --prompt docs/struct_prompt_v4.md --output data/processed/str01_sample100_v4_results.jsonl
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
FULL_RAW_PATH = REPO_ROOT / "data" / "processed" / "hk_electrical_recent_full.csv"
FAILURES_SUFFIX = "_failures.jsonl"

MAX_ATTEMPTS = 3          # 검증 실패 시 건당 최대 시도 횟수
RATE_LIMIT_WAITS = [15, 30, 60, 120]  # 429/503 백오프(초)

# ── 스키마 정의 (struct_verify.py와 동일) ───────────────────────────
ALLOWED_PARTS = {
    "ELECTRICAL_SYSTEM", "ADAS", "INSTRUMENT_CLUSTER", "PROPULSION_BATTERY",
    "BRAKES_ELECTRONIC", "POWERTRAIN_SW", "NON_ELECTRICAL", "INSUFFICIENT_INFO",
}
ALLOWED_SEVERITY = {"CRITICAL", "SERIOUS", "MODERATE", "MINOR"}
ALLOWED_DRIVING_CONTEXT_V4 = {"주행 중", "정차·주차 중", "시동 시", "불명"}
REQUIRED_KEYS = {"odino", "part_category", "symptoms", "severity",
                 "driving_context", "evidence_quote", "insufficient_info"}
REQUIRED_KEYS_V4 = {"symptoms", "severity", "driving_context",
                     "evidence_quote", "insufficient_info"}


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
        "generationConfig": {"temperature": float(env.get("TEMPERATURE", 0)),
                              "responseMimeType": "application/json"},
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
    if "â" in text or "Ã" in text:  # 전형적 모지바케 시그니처
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


def check_schema(rec, extra_bool_keys=frozenset(), required_keys=REQUIRED_KEYS,
                  check_part_category=True, allowed_driving_context=None):
    errors = []
    missing = (required_keys | extra_bool_keys) - rec.keys()
    if missing:
        errors.append(f"누락 키: {sorted(missing)}")
    if check_part_category and rec.get("part_category") not in ALLOWED_PARTS:
        errors.append(f"part_category 허용값 위반: {rec.get('part_category')!r}")
    if rec.get("severity") not in ALLOWED_SEVERITY:
        errors.append(f"severity 허용값 위반: {rec.get('severity')!r}")
    if allowed_driving_context is not None and rec.get("driving_context") not in allowed_driving_context:
        errors.append(f"driving_context 허용값 위반: {rec.get('driving_context')!r}")
    if not isinstance(rec.get("symptoms"), list):
        errors.append("symptoms가 list가 아님")
    if not isinstance(rec.get("insufficient_info"), bool):
        errors.append(f"insufficient_info가 bool이 아님: {rec.get('insufficient_info')!r}")
    for k in extra_bool_keys:
        if k in rec and not isinstance(rec.get(k), bool):
            errors.append(f"{k}가 bool이 아님: {rec.get(k)!r}")
    return errors


def check_quote(quote: str, cdescr: str) -> bool:
    q_norm, c_norm = normalize_text(quote), normalize_text(cdescr)
    if q_norm and q_norm in c_norm:
        return True
    if len(q_norm) >= 20:
        return q_norm[:20] in c_norm
    return False


# ── v4 전용: COMPDESC 파싱 + 형제 COMPDESC 조회 ─────────────────────
def parse_compdesc(compdesc_raw: str):
    """COMPDESC를 ':'로 잘라 (compdesc1, compdesc2) 반환. 중분류 없으면 "no"."""
    parts = [p.strip() for p in str(compdesc_raw or "").split(":")]
    compdesc1 = parts[0] if parts and parts[0] else str(compdesc_raw or "")
    compdesc2 = parts[1] if len(parts) >= 2 and parts[1] else "no"
    return compdesc1, compdesc2


def build_sibling_map(path: Path) -> dict:
    """ODINO → [(CMPLID, COMPDESC), ...] 전체 인덱스. 항상 원본 전체 파일에서 구축
    (부분표본을 처리할 때도 형제 유무가 정확해야 하므로)."""
    m = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            m.setdefault(r["ODINO"], []).append((r["CMPLID"], r["COMPDESC"]))
    return m


def sibling_compdescs(odino: str, own_cmplid: str, sibling_map: dict) -> list:
    """같은 ODINO의 다른 행 중, UNKNOWN OR OTHER가 아닌(=이미 구체적으로 처리된)
    COMPDESC만 중복 없이 순서대로 반환."""
    seen = []
    for cid, compdesc in sibling_map.get(odino, []):
        if cid == own_cmplid:
            continue
        c1, _ = parse_compdesc(compdesc)
        if c1 == "UNKNOWN OR OTHER":
            continue
        if compdesc not in seen:
            seen.append(compdesc)
    return seen


def build_v4_input_header(compdesc1: str, compdesc2: str, odino: str, cmplid: str,
                           sibling_map: dict) -> str:
    lines = [f"COMPDESC 대분류: {compdesc1}", f"COMPDESC 중분류: {compdesc2}"]
    if compdesc1 == "UNKNOWN OR OTHER":
        sibs = sibling_compdescs(odino, cmplid, sibling_map)
        if sibs:
            lines.append(f"형제 COMPDESC: {', '.join(sibs)} (같은 신고의 다른 행에서 이미 처리됨)")
    return "\n".join(lines) + "\n"


# ── 건별 구조화 ──────────────────────────────────────────────────────
def structurize_one(record_id, cdescr, base_prompt, env, extra_bool_keys=frozenset(),
                     input_header=None, required_keys=REQUIRED_KEYS,
                     check_part_category=True, allowed_driving_context=None,
                     allow_empty_quote_when_insufficient=False):
    """반환: (통과 레코드 | None, 통계 {attempts, errors})
    input_header가 주어지면(v4) 그 헤더+CDESCR로 입력을 구성하고, odino/part_category
    보정은 건너뛴다. None이면(v2/v3) 기존 ODINO/CDESCR 입력 방식을 그대로 쓴다."""
    stats = {"attempts": 0, "errors": []}
    feedback = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        stats["attempts"] = attempt
        if input_header is not None:
            body = f"{input_header}CDESCR: {cdescr}"
        else:
            body = f"ODINO: {record_id}\nCDESCR: {cdescr}"
        prompt = f"{base_prompt}\n\n---\n\n**입력:**\n{body}{feedback}"
        raw = call_llm(prompt, env)
        # JSON 파싱 (마크다운 펜스 방어)
        raw_clean = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        try:
            rec = json.loads(raw_clean)
        except json.JSONDecodeError as e:
            stats["errors"].append(f"시도{attempt}: JSON 파싱 실패 ({e})")
            feedback = "\n\n[재시도 지시] 직전 응답이 유효한 JSON이 아니었다. 코드펜스·설명 없이 JSON 객체 하나만 출력하라."
            continue
        if input_header is None:
            rec["odino"] = str(rec.get("odino", record_id)) or record_id
            # 스키마 허용값에 괄호 설명이 붙어 있어 LLM이 통째로 복사하는 경우 정규화
            # 예: 'ADAS(전방충돌·차선·후방카메라 등 운전보조)' → 'ADAS'
            pc = rec.get("part_category")
            if isinstance(pc, str) and "(" in pc:
                rec["part_category"] = pc.split("(")[0].strip()
        errs = check_schema(rec, extra_bool_keys, required_keys=required_keys,
                             check_part_category=check_part_category,
                             allowed_driving_context=allowed_driving_context)
        quote = rec.get("evidence_quote", "")
        skip_quote_check = (allow_empty_quote_when_insufficient
                             and rec.get("insufficient_info") is True and quote == "")
        if not skip_quote_check and not check_quote(quote, cdescr):
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
    ap.add_argument("--prompt", default=str(PROMPT_PATH),
                    help="프롬프트 파일 경로(기본 v2). v3 지정 시 mentions_existing_recall 필드 검증. "
                         "v4(프롬프트 본문에 'compdesc1' 포함) 지정 시 CMPLID 단위·9필드 스키마로 자동 전환")
    ap.add_argument("--sibling-source", default=str(FULL_RAW_PATH),
                    help="v4 형제 COMPDESC 조회용 원본 전체 CSV 경로(기본 hk_electrical_recent_full.csv). "
                         "--input이 부분표본이어도 형제 유무는 이 파일 전체 기준으로 판단한다.")
    ap.add_argument("--temperature", type=float, default=0,
                    help="LLM temperature(기본 0=운영 기본값). STR-03 자기일관성 검사처럼 "
                         "일부러 판단 흔들림을 드러내고 싶을 때만 0보다 크게 지정")
    args = ap.parse_args()

    env = load_env()
    env["TEMPERATURE"] = str(args.temperature)
    base_prompt = Path(args.prompt).read_text(encoding="utf-8")
    is_v4 = "compdesc1" in base_prompt
    # 프롬프트가 mentions_existing_recall을 요구하면(v3) 그 bool 필드를 필수로 검증
    extra_bool_keys = frozenset(
        {"mentions_existing_recall"} if "mentions_existing_recall" in base_prompt else set())
    out_path = Path(args.output)
    fail_path = out_path.with_name(out_path.stem + FAILURES_SUFFIX)

    # 입력 로드
    with open(args.input, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f)]
    if args.limit:
        rows = rows[: args.limit]

    id_key = "cmplid" if is_v4 else "odino"
    # 이어하기: 기존 출력의 id_key 스킵
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(str(json.loads(line)[id_key]))

    row_id_col = "CMPLID" if is_v4 else "ODINO"
    todo = [r for r in rows if str(r[row_id_col]) not in done]
    print(f"입력 {len(rows)}건 / 기존 처리 {len(rows) - len(todo)}건 / 이번 처리 {len(todo)}건")
    print(f"PROVIDER={env.get('PROVIDER', 'gemini')}, MODEL={env.get('GEMINI_MODEL', 'gemini-3.5-flash')}, "
          f"TEMPERATURE={args.temperature}, SCHEMA={'v4' if is_v4 else 'v2/v3'}\n")

    sibling_map = build_sibling_map(Path(args.sibling_source)) if is_v4 else None

    n_ok, n_fail, n_retried, t0 = 0, 0, 0, time.time()
    with open(out_path, "a", encoding="utf-8") as fout, \
         open(fail_path, "a", encoding="utf-8") as ffail:
        for i, row in enumerate(todo, 1):
            cdescr = fix_mojibake(str(row["CDESCR"]))

            if is_v4:
                cmplid = str(row["CMPLID"])
                odino = str(row["ODINO"])
                compdesc1, compdesc2 = parse_compdesc(row["COMPDESC"])
                input_header = build_v4_input_header(compdesc1, compdesc2, odino, cmplid, sibling_map)
                rec, stats = structurize_one(
                    cmplid, cdescr, base_prompt, env,
                    input_header=input_header,
                    required_keys=REQUIRED_KEYS_V4,
                    check_part_category=False,
                    allowed_driving_context=ALLOWED_DRIVING_CONTEXT_V4,
                    allow_empty_quote_when_insufficient=True,
                )
                if rec:
                    rec = {
                        "cmplid": cmplid, "odino": odino,
                        "compdesc1": compdesc1, "compdesc2": compdesc2,
                        "symptoms": rec.get("symptoms"), "severity": rec.get("severity"),
                        "driving_context": rec.get("driving_context"),
                        "evidence_quote": rec.get("evidence_quote"),
                        "insufficient_info": rec.get("insufficient_info"),
                    }
                record_label = cmplid
                ok_desc = f"{compdesc1}/{rec['severity']}" if rec else ""
            else:
                odino = str(row["ODINO"])
                rec, stats = structurize_one(odino, cdescr, base_prompt, env, extra_bool_keys)
                record_label = odino
                ok_desc = f"{rec['part_category']}/{rec['severity']}" if rec else ""

            if rec:
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fout.flush()
                n_ok += 1
                if stats["attempts"] > 1:
                    n_retried += 1
                flag = f" (재시도 {stats['attempts'] - 1}회)" if stats["attempts"] > 1 else ""
                print(f"  [{i}/{len(todo)}] {record_label} OK — {ok_desc}{flag}")
            else:
                ffail.write(json.dumps({id_key: record_label, "errors": stats["errors"]},
                                       ensure_ascii=False) + "\n")
                ffail.flush()
                n_fail += 1
                print(f"  [{i}/{len(todo)}] {record_label} FAIL — {stats['errors'][-1]}")

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
