#!/usr/bin/env python3
"""
molit_parse.py — 국토부 보도자료 txt 파싱 → molit_recalls.csv
입력: data/processed/molit_txt/*.txt
출력: data/processed/molit_recalls.csv
       data/processed/molit_parse_failures.txt (파싱 실패 문단)
"""
import re
import pandas as pd
from pathlib import Path

TXT_DIR = Path("data/processed/molit_txt")
OUT_CSV = Path("data/processed/molit_recalls.csv")
FAIL_TXT = Path("data/processed/molit_parse_failures.txt")

# ──────────────────────────────────────────────
# 파일명 → 발표일 추론
# ──────────────────────────────────────────────
def filename_to_date(stem: str) -> str | None:
    m = re.match(r"^(\d+)", stem)
    if not m:
        return None
    digits = m.group(1)
    if len(digits) == 6:            # YYMMDD
        yy, mm, dd = digits[:2], digits[2:4], digits[4:6]
        return f"20{yy}-{mm}-{dd}"
    if len(digits) == 7 and digits.startswith("25"):   # 250MMDD (2025)
        mm, dd = digits[3:5], digits[5:7]
        return f"2025-{mm}-{dd}"
    return None

# ──────────────────────────────────────────────
# 본문에서 보도 일시 추출 (우선순위)
# ──────────────────────────────────────────────
DATE_PAT = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일")

def extract_press_date(text: str) -> str | None:
    # "보도 일시" 또는 "보도일시" 근처 첫 번째 날짜 우선
    for line in text.splitlines():
        if "보도" in line and ("일시" in line or "시간" in line):
            m = DATE_PAT.search(line)
            if m:
                y, mo, d = m.groups()
                return f"{y}-{int(mo):02d}-{int(d):02d}"
    # 전체 텍스트 첫 번째 날짜
    m = DATE_PAT.search(text)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None

# ──────────────────────────────────────────────
# 리콜 항목 분리 (①②③... 기준)
# ──────────────────────────────────────────────
# ①~⑳ 유니코드 블록: U+2460~U+2473
CIRCLED = "".join(chr(c) for c in range(0x2460, 0x2474))   # ①~⑳
SPLIT_PAT = re.compile(rf"(?=[{re.escape(CIRCLED)}])")

def split_items(text: str) -> list[str]:
    parts = SPLIT_PAT.split(text)
    # 첫 조각은 머리말(날짜·제목 등) — 리콜 항목 아님
    items = [p.strip() for p in parts[1:] if p.strip()]
    return items

# ──────────────────────────────────────────────
# 단일 리콜 항목 파싱
# ──────────────────────────────────────────────
# 패턴 예: ① (현대자동차) 투싼(TUCSON) 등 2개 차종 54,792대는
#           계기판 소프트웨어 결함으로 인해 속도계 정보 표시 오류 가능성이 있어
#           2026년 7월 10일부터 시정조치(소프트웨어 업데이트)를 시행합니다.

MFR_PAT  = re.compile(r"[\(（]([가-힣A-Za-z0-9·\s]+?)[\)）]")
MODEL_PAT = re.compile(r"[\)）]\s*([가-힣A-Za-z0-9·\-\(\)（）\s]+?)(?:등\s*\d|대는|\d+개\s*차종)")
COUNT_PAT = re.compile(r"([\d,]+)\s*대")
CAUSE_PAT = re.compile(r"대[는의]\s*(.+?)\s*(?:으로\s*인해|로\s*인해|설계\s*미흡으로)")
SYMPT_PAT = re.compile(r"(?:인해|으로)\s*(.+?)\s*가능성")
RDATE_PAT = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일부터\s*시정")
RDATE_SHORT = re.compile(r"(\d{1,2})월\s*(\d{1,2})일부터\s*(?:시정|OTA)")

SW_KEYWORDS = ["소프트웨어", "sw", "ecm", "ecu", "ota", "펌웨어", "제어기", "전자제어",
               "전장", "통신", "모듈", "인포테인먼트", "디스플레이", "계기판", "클러스터"]

def is_sw_related(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in SW_KEYWORDS)

def parse_item(item_text: str) -> dict | None:
    # 제조사: 첫 번째 괄호 내용
    mfr_m = MFR_PAT.search(item_text)
    manufacturer = mfr_m.group(1).strip() if mfr_m else ""

    # 대수
    count_m = COUNT_PAT.search(item_text)
    unit_count_raw = count_m.group(1).replace(",", "") if count_m else ""
    unit_count = int(unit_count_raw) if unit_count_raw.isdigit() else None

    # 원인 (대는 ~ 으로/이/가)
    cause_m = CAUSE_PAT.search(item_text)
    cause = cause_m.group(1).strip() if cause_m else ""

    # 증상 (가능성 앞)
    sympt_m = SYMPT_PAT.search(item_text)
    symptom = sympt_m.group(1).strip() if sympt_m else ""

    # 시정시작일
    rdate_m = RDATE_PAT.search(item_text)
    if rdate_m:
        y, mo, d = rdate_m.groups()
        remedy_start = f"{y}-{int(mo):02d}-{int(d):02d}"
    else:
        remedy_start = ""

    # 차종: 제조사 괄호 직후 ~ "등 N개 차종" 직전
    model_raw = ""
    if mfr_m:
        after_mfr = item_text[mfr_m.end():]
        model_m = re.match(r"\s*([가-힣A-Za-z0-9·\-\(\)（）\s]+?)(?=등\s*\d|\d+개\s*차종|대는)", after_mfr)
        if model_m:
            model_raw = model_m.group(1).strip()
        else:
            # 대수 직전까지
            cnt_pos = COUNT_PAT.search(after_mfr)
            if cnt_pos:
                model_raw = after_mfr[:cnt_pos.start()].strip()

    if unit_count is None:
        return None  # 대수 없으면 리콜 항목 아님

    return {
        "제조사": manufacturer,
        "차종_원문": model_raw,
        "대수": unit_count,
        "원인": cause,
        "증상": symptom,
        "시정시작일": remedy_start,
        "sw관련": is_sw_related(item_text),
        "_raw": item_text[:300],
    }


# ──────────────────────────────────────────────
# preamble(첫 ① 이전) 서술형 리콜 추출
# ──────────────────────────────────────────────
PREAMBLE_MFR_PAT = re.compile(
    r"(현대자동차|기아자동차|현대|기아|케이지모빌리티)(?:㈜|주식회사)?"
)

def parse_preamble_recalls(preamble: str, press_date: str, stem: str) -> list[dict]:
    """□ 단락 서술형 리콜 추출 (원 번호 없는 형식)"""
    text = re.sub(r"\s+", " ", preamble)
    if not COUNT_PAT.search(text) or "가능성" not in text:
        return []

    results = []
    mfr_m = PREAMBLE_MFR_PAT.search(text)
    manufacturer = mfr_m.group(1) if mfr_m else ""

    count_m = COUNT_PAT.search(text)
    unit_count_raw = count_m.group(1).replace(",", "") if count_m else ""
    unit_count = int(unit_count_raw) if unit_count_raw.isdigit() else None
    if unit_count is None:
        return []

    # 차종: 제조사 이후 ~ 등/대수 이전
    model_raw = ""
    if mfr_m:
        after = text[mfr_m.end():]
        # "는 팰리세이드 등" 또는 "㈜는 팰리세이드"
        m = re.match(r"[^가-힣]*([가-힣A-Za-z0-9\s]+?)(?=등|\d+개\s*차종|\d[\d,]*대)", after)
        if m:
            model_raw = m.group(1).strip()

    cause_m = re.search(r"대[는의]\s*(.+?)\s*(?:으로\s*인해|로\s*인해|설계\s*미흡으로)", text)
    cause = cause_m.group(1).strip() if cause_m else ""

    sympt_m = SYMPT_PAT.search(text)
    symptom = sympt_m.group(1).strip() if sympt_m else ""

    # 시정시작일: 연도 있는 패턴 먼저, 없으면 press_date 연도 보정
    rdate_m = RDATE_PAT.search(text)
    if rdate_m:
        y, mo, d = rdate_m.groups()
        remedy_start = f"{y}-{int(mo):02d}-{int(d):02d}"
    else:
        short_m = RDATE_SHORT.search(text)
        if short_m and press_date:
            year = press_date[:4]
            mo, d = short_m.groups()
            remedy_start = f"{year}-{int(mo):02d}-{int(d):02d}"
        else:
            remedy_start = ""

    results.append({
        "발표일": press_date,
        "출처파일": stem,
        "제조사": manufacturer,
        "차종_원문": model_raw,
        "대수": unit_count,
        "원인": cause,
        "증상": symptom,
        "시정시작일": remedy_start,
        "sw관련": is_sw_related(text),
        "_raw": text[:300],
    })
    return results


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────
def main():
    txts = sorted(TXT_DIR.glob("*.txt"))
    if not txts:
        print(f"txt 파일 없음: {TXT_DIR} — molit_extract.py 먼저 실행하세요")
        return

    records = []
    failures = []

    for txt_path in txts:
        text = txt_path.read_text(encoding="utf-8")
        stem = txt_path.stem

        # 발표일: 본문 우선, 파일명 폴백
        press_date = extract_press_date(text) or filename_to_date(stem) or ""

        # preamble(첫 ① 이전) 서술형 리콜 먼저 추출
        raw_parts = SPLIT_PAT.split(text)
        preamble = raw_parts[0] if raw_parts else ""
        pre_recalls = parse_preamble_recalls(preamble, press_date, stem)
        records.extend(pre_recalls)

        items = split_items(text)
        if not items and not pre_recalls:
            failures.append(f"=== {stem} (항목 분리 실패) ===\n{text[:500]}\n")
            continue

        file_parsed = len(pre_recalls)
        for item in items:
            parsed = parse_item(item)
            if parsed:
                parsed["발표일"] = press_date
                parsed["출처파일"] = stem
                records.append(parsed)
                file_parsed += 1
            else:
                failures.append(f"=== {stem} — 항목 파싱 실패 ===\n{item[:400]}\n")

        print(f"  {stem}: 발표일={press_date}, 항목 {file_parsed}/{len(items)} 파싱")

    # CSV 저장
    if records:
        df = pd.DataFrame(records)
        # 컬럼 순서 정리
        cols = ["발표일", "출처파일", "제조사", "차종_원문", "대수", "원인", "증상",
                "시정시작일", "sw관련", "_raw"]
        df = df[[c for c in cols if c in df.columns]]
        df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
        print(f"\n✓ molit_recalls.csv 저장: {len(df)}행 × {len(df.columns)}열")
        print(f"  발표일 범위: {df['발표일'].min()} ~ {df['발표일'].max()}")
        print(f"  제조사 분포:\n{df['제조사'].value_counts().head(10).to_string()}")
        print(f"  SW관련 비율: {df['sw관련'].sum()}/{len(df)} ({df['sw관련'].mean():.1%})")
    else:
        print("⚠  파싱된 레코드 없음")

    # 실패 로그
    if failures:
        FAIL_TXT.write_text("\n".join(failures), encoding="utf-8")
        print(f"\n⚠  파싱 실패 {len(failures)}건 → {FAIL_TXT}")
    else:
        print("\n✓ 파싱 실패 0건")


if __name__ == "__main__":
    main()
