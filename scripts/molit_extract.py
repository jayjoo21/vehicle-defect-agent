#!/usr/bin/env python3
"""
molit_extract.py — 국토부 보도자료 PDF 텍스트 추출
pdfplumber로 docs/molit_press/*.pdf → data/processed/molit_txt/*.txt
"""
import subprocess, sys

try:
    import pdfplumber
except ImportError:
    print("pdfplumber 미설치 → pip install 중...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pdfplumber"])
    import pdfplumber

from pathlib import Path

PDF_DIR = Path("docs/molit_press")
OUT_DIR = Path("data/processed/molit_txt")
OUT_DIR.mkdir(parents=True, exist_ok=True)

pdfs = sorted(PDF_DIR.glob("*.pdf"))
print(f"PDF 총 {len(pdfs)}개 발견\n")

zero_char_files = []
results = []

for pdf_path in pdfs:
    out_path = OUT_DIR / (pdf_path.stem + ".txt")
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages_text = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages_text.append(text)
            full_text = "\n\n".join(pages_text)
        out_path.write_text(full_text, encoding="utf-8")
        char_count = len(full_text)
        results.append((pdf_path.name, char_count, None))
        if char_count == 0:
            zero_char_files.append(pdf_path.name)
            print(f"  [WARN] {pdf_path.name}: 0자 (스캔본 가능성)")
        else:
            print(f"  [OK]   {pdf_path.name}: {char_count:,}자")
    except Exception as e:
        results.append((pdf_path.name, -1, str(e)))
        print(f"  [ERR]  {pdf_path.name}: 오류 - {e}")

success = sum(1 for _, c, e in results if c > 0 and e is None)
print(f"\n완료: {success}/{len(pdfs)} 추출 성공")
if zero_char_files:
    print(f"[WARN] 0자 파일 {len(zero_char_files)}개 (스캔본 의심):")
    for f in zero_char_files:
        print(f"   {f}")
