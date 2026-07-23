# -*- coding: utf-8 -*-
"""
str04_judge_pipeline.py — 차량 결함 신고 채점(Judge) Agent 파이프라인 (담당: 상진, 팀원 제공분 이식)

data/samples/grading_sheet_v4.csv(수동 채점표)가 사람이 채워야 했던 항목을
LLM Judge로 자동화한다. STR-01(v4)이 만든 구조화 출력(LLM_증상/LLM_근거인용/
LLM_정보부족여부)을 CDESCR 원문과 대조해 채점자가 직접 판정한다.

[구현 기능]
    JDG-01  제약된 Judge      : struct_prompt_v4.md 스키마/규칙 안에서만 채점,
                               CDESCR 에 없는 내용 차단(verbatim 검증)
    JDG-02  Self-Consistency : 병렬 5회 반복 → 필드별 다수결,
                               다수결 == JDG-01 이면 uncertainty_flag=TRUE, 아니면 FALSE
    JDG-03  Judge 신뢰도      : gold 대조 3개 컬럼 일치율(소수점 넷째 자리 반올림)

[설치]
    pip install google-genai pandas pydantic python-dotenv

[실행]
    python scripts/str04_judge_pipeline.py
    (경로는 REPO_ROOT 기준으로 계산 — 실행 위치와 무관)

[API 키]
    코드에 하드코딩하지 않는다. 아래 중 하나로 제공:
      A) 레포 루트에 .env 파일:  GEMINI_API_KEY=발급받은키   (.gitignore에 이미 포함됨)
      B) 환경변수 GEMINI_API_KEY 또는 GOOGLE_API_KEY
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Literal, Optional

import pandas as pd
from pydantic import BaseModel, Field

from google import genai
from google.genai import types


# =============================================================================
# 0. 경로 설정 (REPO_ROOT 기준 — 다른 str0x 스크립트와 동일한 규칙)
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = REPO_ROOT / "data" / "samples"
OUTPUT_DIR = REPO_ROOT / "data" / "processed"

INPUT_CSV = INPUT_DIR / "str01_sample20_v4_grading.csv"
GOLD_CSV = INPUT_DIR / "str01_sample20_v4_grading_gold.csv"
PROMPT_MD = REPO_ROOT / "docs" / "struct_prompt_v4.md"
OUTPUT_CSV = OUTPUT_DIR / "str01_sample20_v4_grading_final.csv"

# CSV 인코딩: 아래 후보를 순서대로 시도해 자동 판별
#   (입력본은 UTF-8(BOM), gold 는 CP949/EUC-KR 로 저장돼 있어 서로 다름)
CSV_ENCODING_CANDIDATES = ["utf-8-sig", "cp949", "utf-8", "euc-kr"]
OUTPUT_ENCODING = "utf-8-sig"   # Excel 에서 한글이 깨지지 않는 인코딩


# =============================================================================
# 1. API Key / 모델 설정
# =============================================================================

MODEL = "gemini-2.5-flash"

# temperature
#   - JDG-01(기준 판정)은 운영 기본값 0.0
#   - JDG-02 자기일관성 5회는 다수결/불확실성 측정이 의미를 가지려면 표본 다양성이 필요하므로
#     별도 온도(기본 0.7) 사용. 완전 결정론으로 돌리려면 SC_TEMPERATURE = 0.0 으로 변경
#     (단, 그 경우 5회가 거의 동일해져 uncertainty_flag 가 대부분 TRUE 가 됨)
JDG01_TEMPERATURE: float = 0.0
SC_TEMPERATURE: float = 0.7
SC_RUNS: int = 5

THINKING_BUDGET: int = -1   # 2.5 Flash: -1 동적, 0 비활성, 그 외 상한 토큰
MAX_WORKERS: int = 8        # 병렬 스레드 수 (429 rate limit 발생 시 4 이하로 낮추세요)
MAX_RETRIES: int = 3        # 호출/파싱 실패 시 재시도 횟수


# =============================================================================
# 2. 컬럼명 상수
# =============================================================================

COL_CMPLID = "원본_cmplid"
COL_ODINO = "원본_odino"
COL_COMP1 = "원본_COMPDESC대분류"
COL_COMP2 = "원본_COMPDESC중분류"
COL_CDESCR = "원본_신고원문(CDESCR)"
COL_LLM_SYMPTOM = "LLM_증상"
COL_LLM_QUOTE = "LLM_근거인용"
COL_LLM_INSUFF = "LLM_정보부족여부"

COL_G_SEVERITY = "채점_심각도(내판단)"
COL_G_SYMPTOM = "채점_증상부합(O/X)"
COL_G_INSUFF = "채점_정보부족맞음(O/X)"
COL_G_MEMO = "채점_메모"

COL_FINAL_DECISION = "final_decision"
COL_VERIFIED_QUOTE = "verified_quote"
COL_UNCERTAINTY = "uncertainty_flag"

UNKNOWN_CAT = "UNKNOWN OR OTHER"
SEVERITY_ORDER = ["MINOR", "MODERATE", "SERIOUS", "CRITICAL"]   # 동점 시 tie-break 기준


# =============================================================================
# 3. 로컬 환경 준비 (콘솔 인코딩 / .env / 파일 존재 확인)
# =============================================================================

def setup_console() -> None:
    """Windows 콘솔에서 한글·이모지 출력이 깨지지 않도록 UTF-8 로 전환."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_api_key() -> str:
    """우선순위: 환경변수 GEMINI_API_KEY / GOOGLE_API_KEY → 레포 루트 .env 파일."""
    # python-dotenv 가 설치돼 있으면 레포 루트의 .env 를 로드
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        # dotenv 미설치 시 .env 를 직접 최소 파싱
        env_path = REPO_ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    return key.strip()


def check_files() -> None:
    """실행 전에 입력 파일 3종이 제자리에 있는지 확인하고, 없으면 명확히 안내."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not INPUT_DIR.exists():
        raise FileNotFoundError(
            f"input 폴더가 없습니다: {INPUT_DIR}\n"
            f"  → data/samples 폴더에 데이터 파일들을 넣어주세요."
        )

    missing = [p.name for p in (INPUT_CSV, GOLD_CSV, PROMPT_MD) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"필요한 입력 파일을 찾을 수 없습니다: {', '.join(missing)}\n"
            f"  기대 경로: {INPUT_CSV}, {GOLD_CSV}, {PROMPT_MD}"
        )


def read_csv_auto(path: Path) -> pd.DataFrame:
    """인코딩을 자동 판별해 CSV 를 읽는다 (입력본 UTF-8, gold CP949 혼재 대응)."""
    last_err: Optional[Exception] = None
    for enc in CSV_ENCODING_CANDIDATES:
        try:
            df = pd.read_csv(path, encoding=enc)
            # 한글 컬럼명이 깨지지 않았는지 확인 (깨지면 다음 후보로)
            if COL_CDESCR in df.columns:
                print(f"    · {path.name}  (encoding={enc}, {len(df)}행)")
                return df
        except (UnicodeDecodeError, LookupError) as e:
            last_err = e
        except Exception as e:
            last_err = e
    raise RuntimeError(f"CSV 인코딩 판별 실패: {path}\n  마지막 오류: {last_err}")


def read_text_auto(path: Path) -> str:
    """프롬프트 md 를 인코딩 자동 판별해 읽는다."""
    for enc in ["utf-8-sig", "utf-8", "cp949"]:
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"텍스트 인코딩 판별 실패: {path}")


# =============================================================================
# 4. 출력 스키마 (제약된 Judge 의 구조화 출력 강제)
# =============================================================================

class JudgeResult(BaseModel):
    """Gemini 가 반드시 이 스키마로만 응답하도록 response_schema 로 주입."""
    graded_severity: Literal["CRITICAL", "SERIOUS", "MODERATE", "MINOR"] = Field(
        ..., description="채점자가 CDESCR 과 COMPDESC 만 보고 가이드라인에 따라 직접 판단한 심각도"
    )
    severity_reason: str = Field(..., description="심각도 판정 이유(가이드·규칙①②③ 반영, 서술형)")

    symptom_match: bool = Field(..., description="LLM_증상 이 CDESCR 의 이상 상황을 잘 설명하면 true")
    symptom_match_reason: str = Field(..., description="증상부합 판정 이유(true 면 '이상 없음')")

    insufficient_correct: bool = Field(..., description="LLM_정보부족여부 판단이 올바르면 true")
    insufficient_reason: str = Field(..., description="정보부족 판정이 맞/틀린 이유(서술형)")

    final_decision: Literal["결함", "미결함"] = Field(
        ..., description="이 COMPDESC 측면에 실제 결함이 있으면 '결함', 아니면 '미결함'"
    )
    verified_quote: str = Field(
        ..., description="판단 근거가 된 CDESCR 원문 문장 1개(verbatim). 근거 없으면 빈 문자열"
    )


# =============================================================================
# 5. 프롬프트 구성
# =============================================================================

def build_system_instruction(rulebook: str) -> str:
    """struct_prompt_v4.md 전문을 규칙서로 주입한 '제약된 Judge' 시스템 프롬프트."""
    return f"""당신은 차량 결함 신고 채점(Judge) AI다. 아래 <규칙서>에 기록된 스키마와 규칙 '안에서만' 채점한다.

[절대 준수 사항 — 제약]
1. 오직 주어진 CDESCR(신고원문) 안에 실제로 존재하는 내용만 근거로 삼는다.
   CDESCR 에 없는 사실·증상·상황을 추측하거나 지어내지 말 것. 외부 지식으로 보완하지 말 것.
2. verified_quote 는 반드시 CDESCR 원문에 '연속된 문자열 그대로(verbatim)' 존재해야 한다.
   요약·의역·짜깁기 금지. 근거가 없으면 빈 문자열("")로 둔다.
3. 심각도(graded_severity)는 채점자로서 '직접' 판단한다. LLM 이 낸 심각도 값은 입력에 주지 않으며,
   너도 그것을 가정하지 말고 <규칙서>의 severity 기준과 추가 규칙 ①②③, 통제 가능성 상한을
   순서대로 적용해 CDESCR 과 COMPDESC 앵커만으로 판정한다.
4. 판정은 반드시 이번 호출에서 주어진 COMPDESC 대분류·중분류가 가리키는 결함 측면에 한정한다
   (<규칙서>의 'COMPDESC 앵커링' 참조). 그 밖의 결함 서술은 이번 판단 대상이 아니다.

[채점 항목]
- graded_severity / severity_reason :
    CDESCR + COMPDESC 앵커만으로 CRITICAL / SERIOUS / MODERATE / MINOR 중 하나를 직접 판정.
    이유는 가이드라인과 추가 규칙(①결함-결과 분리, ②통제 가능성 상한, ③오작동>미작동)을 명시적으로 반영해 서술.
- symptom_match / symptom_match_reason :
    입력으로 주어진 'LLM_증상' 이 CDESCR 의 이상 상황을 잘 설명하면 true(이유엔 '이상 없음'),
    이질적이거나 틀렸으면 false(왜 틀렸는지 서술).
- insufficient_correct / insufficient_reason :
    입력으로 주어진 'LLM_정보부족여부' 와 'LLM_근거인용' 을 CDESCR 에 비추어,
    그 정보부족 판단이 올바르면 true, 아니면 false. 이유를 서술.
- final_decision :
    이 COMPDESC 측면에서 CDESCR 이 실제 결함 증상을 서술하면 '결함',
    (리콜·행정 항의뿐이거나, 이 측면의 결함 단서가 없어) 결함으로 볼 수 없으면 '미결함'.
- verified_quote :
    위 판정의 핵심 근거가 된 CDESCR 원문 문장 1개(verbatim). 근거가 없으면 "".

반드시 JudgeResult JSON 스키마 형식으로만 응답한다.

<규칙서 (struct_prompt_v4.md 전문)>
{rulebook}
</규칙서>"""


def build_user_content(row: pd.Series, sibling_str: Optional[str]) -> str:
    """행 1건에 대한 채점 입력. (주의) LLM_심각도·LLM_발생상황은 일부러 넣지 않는다."""
    comp1 = str(row[COL_COMP1]).strip()
    comp2 = str(row[COL_COMP2]).strip()
    cdescr = str(row[COL_CDESCR]).strip()
    llm_symptom = str(row[COL_LLM_SYMPTOM]).strip()
    llm_quote = str(row[COL_LLM_QUOTE]).strip()
    llm_insuff = str(row[COL_LLM_INSUFF]).strip()

    lines = [
        f"COMPDESC 대분류: {comp1}",
        f"COMPDESC 중분류: {comp2}",
    ]
    # 형제 COMPDESC 줄은 대분류가 UNKNOWN OR OTHER 이고 실제 형제가 있을 때만 등장
    if comp1.upper() == UNKNOWN_CAT and sibling_str:
        lines.append(f"형제 COMPDESC: {sibling_str} (같은 신고의 다른 행에서 이미 처리됨)")

    lines += [
        "",
        "CDESCR (신고원문, 영문 원문 그대로 읽고 해석):",
        cdescr,
        "",
        "── 아래는 채점 대상 LLM 출력 (심각도 채점에는 사용 금지) ──",
        f"[LLM_증상] {llm_symptom}",
        f"[LLM_정보부족여부] {llm_insuff}",
        f"[LLM_근거인용] {llm_quote}",
        "",
        "위 지침과 <규칙서>에 따라 이 건을 채점해 JudgeResult JSON 으로 응답하라.",
    ]
    return "\n".join(lines)


# =============================================================================
# 6. Gemini 호출
# =============================================================================

def make_client() -> genai.Client:
    key = load_api_key()
    if not key:
        raise RuntimeError(
            "Gemini API Key 가 설정돼 있지 않습니다.\n"
            "  방법 A) 레포 루트에 .env 파일을 만들고:  GEMINI_API_KEY=발급받은키\n"
            "  방법 B) 환경변수 GEMINI_API_KEY 를 설정\n"
            f"  (.env 예상 위치: {REPO_ROOT / '.env'})"
        )
    return genai.Client(api_key=key)


def call_judge(
    client: genai.Client,
    system_instruction: str,
    user_content: str,
    cdescr: str,
    temperature: float,
) -> JudgeResult:
    """Gemini 1회 호출 → JudgeResult. 실패 시 재시도. verified_quote verbatim 검증까지 수행."""
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=temperature,
        response_mime_type="application/json",
        response_schema=JudgeResult,
        thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
    )

    last_err: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.models.generate_content(
                model=MODEL, contents=user_content, config=config
            )
            # SDK 가 파싱해 준 pydantic 인스턴스 우선 사용, 없으면 text 파싱
            result: Optional[JudgeResult] = getattr(resp, "parsed", None)
            if result is None:
                result = JudgeResult(**json.loads(resp.text))

            # --- 제약: CDESCR 에 없는 인용은 차단 ---
            result.verified_quote = verify_quote(result.verified_quote, cdescr)
            return result
        except Exception as e:  # noqa: BLE001  (전송/파싱/검증 오류 모두 재시도)
            last_err = e
            time.sleep(1.5 * attempt)   # 단순 백오프
    raise RuntimeError(f"call_judge 실패(재시도 {MAX_RETRIES}회): {last_err}")


# =============================================================================
# 7. verbatim 검증 & 유틸
# =============================================================================

def _normalize(s: str) -> str:
    """스마트따옴표·공백 정규화 후 소문자화 — verbatim 대조용."""
    s = unicodedata.normalize("NFKC", s)
    s = (s.replace("‘", "'").replace("’", "'")
           .replace("“", '"').replace("”", '"')
           .replace("–", "-").replace("—", "-"))
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def verify_quote(quote: str, cdescr: str) -> str:
    """quote 가 CDESCR 안에 실제로 존재하면 그대로 반환, 아니면 '' (차단)."""
    q = (quote or "").strip()
    if not q:
        return ""
    if _normalize(q) in _normalize(cdescr):
        return q
    return ""   # 원문에 없는 인용 → 차단


def compute_sibling_map(df: pd.DataFrame) -> dict:
    """UNKNOWN OR OTHER 행에 대해 같은 ODINO 의 다른(구체적) COMPDESC 목록을 만든다.
    (이 20행 샘플 내부 기준. 운영에서는 전체 원본 데이터로 조회해야 함.)"""
    sib = {}
    for idx, row in df.iterrows():
        if str(row[COL_COMP1]).strip().upper() != UNKNOWN_CAT:
            sib[idx] = None
            continue
        odino = row[COL_ODINO]
        others = df[(df[COL_ODINO] == odino) & (df.index != idx)]
        tags = []
        for _, o in others.iterrows():
            c1 = str(o[COL_COMP1]).strip()
            if c1.upper() == UNKNOWN_CAT:
                continue   # 형제도 UNKNOWN 이면 참고 가치 없음
            c2 = str(o[COL_COMP2]).strip()
            tags.append(c1 if c2 in ("", "no") else f"{c1}: {c2}")
        sib[idx] = "; ".join(dict.fromkeys(tags)) if tags else None
    return sib


# =============================================================================
# 8. 다수결 (Self-Consistency 집계)
# =============================================================================

def _majority(values: list):
    """최빈값. 동점이면 심각도는 더 높은 등급, 그 외는 첫 등장값으로 tie-break."""
    counts = Counter(values)
    top = counts.most_common()
    best_n = top[0][1]
    tied = [v for v, n in top if n == best_n]
    if len(tied) == 1:
        return tied[0]
    if all(v in SEVERITY_ORDER for v in tied):          # 심각도: 더 위험한 등급 우선
        return max(tied, key=lambda v: SEVERITY_ORDER.index(v))
    for v in values:                                     # 그 외: 먼저 등장한 값
        if v in tied:
            return v
    return tied[0]


def pick_quote(results: list, majority_decision: str, ref_quote: str) -> str:
    """다수결 final_decision 과 일치하는 표본들 중 가장 흔한 비어있지 않은 인용을 채택."""
    cands = [r.verified_quote for r in results
             if r.final_decision == majority_decision and r.verified_quote.strip()]
    if cands:
        return Counter(cands).most_common(1)[0][0]
    if ref_quote.strip():
        return ref_quote
    any_q = [r.verified_quote for r in results if r.verified_quote.strip()]
    return Counter(any_q).most_common(1)[0][0] if any_q else ""


def aggregate(results: list) -> dict:
    """5개 표본 → 필드별 다수결 결과."""
    return {
        "graded_severity": _majority([r.graded_severity for r in results]),
        "symptom_match": _majority([r.symptom_match for r in results]),
        "insufficient_correct": _majority([r.insufficient_correct for r in results]),
        "final_decision": _majority([r.final_decision for r in results]),
    }


def pick_representative(results: list, maj: dict):
    """다수결과 (final_decision, severity) 가 일치하는 대표 표본(메모용). 없으면 첫 표본."""
    for r in results:
        if (r.final_decision == maj["final_decision"]
                and r.graded_severity == maj["graded_severity"]):
            return r
    return results[0]


def build_memo(rep, results: list, maj: dict) -> str:
    """채점_메모: 심각도/증상부합/정보부족 이유 + 자기일관성 표 분포."""
    sym_txt = "이상 없음" if maj["symptom_match"] else rep.symptom_match_reason
    dist = (
        f"심각도 {dict(Counter(r.graded_severity for r in results))}, "
        f"증상부합 {dict(Counter(r.symptom_match for r in results))}, "
        f"정보부족 {dict(Counter(r.insufficient_correct for r in results))}, "
        f"최종 {dict(Counter(r.final_decision for r in results))}"
    )
    return (
        f"[심각도] {rep.severity_reason} "
        f"[증상부합] {sym_txt} "
        f"[정보부족] {rep.insufficient_reason} "
        f"[SC분포] {dist}"
    )


# =============================================================================
# 9. 파이프라인 (JDG-01 + JDG-02)
# =============================================================================

def to_ox(b: bool) -> str:
    return "TRUE" if b else "FALSE"


def process_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    client = make_client()
    rulebook = read_text_auto(PROMPT_MD)
    system_instruction = build_system_instruction(rulebook)
    sibling_map = compute_sibling_map(df)

    # 행별 입력 사전 구성
    prepared = {
        idx: (build_user_content(row, sibling_map[idx]), str(row[COL_CDESCR]))
        for idx, row in df.iterrows()
    }

    # 호출 태스크 평탄화: 행마다 JDG-01 1회(temp=0) + SC 5회
    tasks = []
    for idx in df.index:
        tasks.append((idx, "ref", 0, JDG01_TEMPERATURE))
        for k in range(SC_RUNS):
            tasks.append((idx, "sc", k, SC_TEMPERATURE))

    def run_one(task):
        idx, kind, run_idx, temp = task
        user_content, cdescr = prepared[idx]
        res = call_judge(client, system_instruction, user_content, cdescr, temp)
        return idx, kind, run_idx, res

    ref_results = {}
    sc_results = {idx: [None] * SC_RUNS for idx in df.index}

    total = len(tasks)
    done = 0
    print(f"    총 {total}회 호출 (행 {len(df)} × (기준 1 + SC {SC_RUNS})), "
          f"병렬 {MAX_WORKERS} 스레드")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(run_one, t) for t in tasks]
        for fut in as_completed(futures):
            idx, kind, run_idx, res = fut.result()
            if kind == "ref":
                ref_results[idx] = res
            else:
                sc_results[idx][run_idx] = res
            done += 1
            print(f"\r    진행률 {done}/{total} ({done / total:.0%})", end="", flush=True)
    print()

    # 결과 조립
    out = df.copy()
    # 입력 CSV 의 채점 컬럼은 값이 비어 있어 float64(NaN)로 읽힌다.
    # 최신 pandas 는 float 컬럼에 문자열 대입 시 TypeError 를 내므로 object dtype 으로 먼저 변환.
    for col in (COL_G_SEVERITY, COL_G_SYMPTOM, COL_G_INSUFF, COL_G_MEMO,
                COL_FINAL_DECISION, COL_VERIFIED_QUOTE, COL_UNCERTAINTY):
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].astype("object")

    for idx in df.index:
        ref = ref_results[idx]
        runs = [r for r in sc_results[idx] if r is not None]
        maj = aggregate(runs)
        rep = pick_representative(runs, maj)
        quote = pick_quote(runs, maj["final_decision"], ref.verified_quote)

        # JDG-02 uncertainty_flag : 다수결 == JDG-01(기준) 이면 TRUE, 아니면 FALSE
        ref_key = (ref.final_decision, ref.graded_severity,
                   ref.symptom_match, ref.insufficient_correct)
        maj_key = (maj["final_decision"], maj["graded_severity"],
                   maj["symptom_match"], maj["insufficient_correct"])

        out.at[idx, COL_G_SEVERITY] = maj["graded_severity"]
        out.at[idx, COL_G_SYMPTOM] = to_ox(maj["symptom_match"])
        out.at[idx, COL_G_INSUFF] = to_ox(maj["insufficient_correct"])
        out.at[idx, COL_G_MEMO] = build_memo(rep, runs, maj)
        out.at[idx, COL_FINAL_DECISION] = maj["final_decision"]
        out.at[idx, COL_VERIFIED_QUOTE] = quote
        out.at[idx, COL_UNCERTAINTY] = "TRUE" if ref_key == maj_key else "FALSE"

    return out


# =============================================================================
# 10. JDG-03  신뢰도(일치율) 측정
# =============================================================================

def _to_bool(v):
    if isinstance(v, bool):
        return v
    s = str(v).strip().upper()
    if s in ("TRUE", "T", "O", "1", "Y", "YES"):
        return True
    if s in ("FALSE", "F", "X", "0", "N", "NO"):
        return False
    return None


def _norm_sev(v) -> str:
    return str(v).strip().upper()


def measure_reliability(final_df: pd.DataFrame, gold_df: pd.DataFrame) -> dict:
    """final vs gold 를 원본_cmplid 기준으로 정렬해 3개 채점 컬럼 일치율 산출."""
    merged = final_df.merge(gold_df, on=COL_CMPLID, suffixes=("_pred", "_gold"))
    total = len(merged)
    if total == 0:
        raise ValueError("final 과 gold 의 원본_cmplid 가 하나도 매칭되지 않았습니다.")
    if total != len(final_df):
        print(f"    ⚠ 주의: {len(final_df)}행 중 {total}행만 gold 와 매칭됨")

    rates = {}
    rates[COL_G_SEVERITY] = round(sum(
        _norm_sev(r[f"{COL_G_SEVERITY}_pred"]) == _norm_sev(r[f"{COL_G_SEVERITY}_gold"])
        for _, r in merged.iterrows()
    ) / total, 4)

    for col in (COL_G_SYMPTOM, COL_G_INSUFF):
        rates[col] = round(sum(
            _to_bool(r[f"{col}_pred"]) == _to_bool(r[f"{col}_gold"])
            for _, r in merged.iterrows()
        ) / total, 4)

    return rates


# =============================================================================
# 11. main
# =============================================================================

def main() -> None:
    setup_console()
    print("=" * 60)
    print("  차량 결함 신고 채점 Judge 파이프라인 (JDG-01 / 02 / 03)")
    print("=" * 60)
    print(f"  레포 루트 : {REPO_ROOT}")
    print(f"  입력 폴더 : {INPUT_DIR}")
    print(f"  출력 폴더 : {OUTPUT_DIR}")
    print("-" * 60)

    check_files()

    print("[0] 데이터 로드")
    df = read_csv_auto(INPUT_CSV)

    print(f"\n[JDG-01/02] 채점 시작 "
          f"(모델={MODEL}, 기준 temp={JDG01_TEMPERATURE}, SC temp={SC_TEMPERATURE})")
    final_df = process_dataframe(df)

    final_df.to_csv(OUTPUT_CSV, index=False, encoding=OUTPUT_ENCODING)
    print(f"[JDG-02] 저장 완료 → {OUTPUT_CSV}")

    print("\n[JDG-03] gold 대조 일치율 측정")
    gold_df = read_csv_auto(GOLD_CSV)
    rates = measure_reliability(final_df, gold_df)

    print("-" * 60)
    for col, r in rates.items():
        print(f"    {col:<22} 일치율 = {r:.4f}")
    print("-" * 60)
    print("완료.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        setup_console()
        print(f"\n[오류] {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
