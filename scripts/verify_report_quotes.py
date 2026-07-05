"""
report_24V757000.md / report_false_alarm.md 의 대표 원문 인용이 실제 CDESCR 원문에
verbatim으로 존재하는지 검증.
"""
import re
import pandas as pd

SOURCE_CSV = "data/processed/hk_electrical_recent_full.csv"

QUOTES = [
    ("report_24V757000.md", "11616811",
     "the instrument cluster screen would remain black, preventing the driver from seeing the speedometer, "
     "vehicle state of charge, warning lights, etc and making the vehicle dangerous to drive."),
    ("report_24V757000.md", "11615661",
     "I had to drive home for one hour with no information on speed, range, cameras, proximity sensors, etc."),
    ("report_24V757000.md", "11616449",
     "while driving 55 MPH, the turn signals became inoperable while attempting to switch lanes."),
    ("report_false_alarm.md", "11581731",
     "The contact had not experienced a failure."),
    ("report_false_alarm.md", "11581934",
     "while driving at approximately 35 MPH, the vehicle lost motive power, shut off but was able to coast off the highway."),
    ("report_false_alarm.md", "11585229",
     "she heard an abnormal sound coming from the engine compartment, after which she observed smoke coming "
     "from the engine compartment before the vehicle lost electrical power."),
]


def normalize(text):
    return re.sub(r"\s+", " ", text).strip()


def main():
    src = pd.read_csv(SOURCE_CSV, encoding="utf-8-sig", dtype=str)
    cdescr_map = dict(zip(src["ODINO"], src["CDESCR"]))

    all_ok = True
    for report, odino, quote in QUOTES:
        cdescr = cdescr_map.get(odino, "")
        ok = normalize(quote) in normalize(cdescr)
        all_ok &= ok
        status = "OK" if ok else "MISMATCH"
        print(f"[{status}] {report} ODINO={odino}")
        if not ok:
            print(f"  quote : {quote}")
            print(f"  cdescr: {normalize(cdescr)[:200]}")

    print(f"\n총 {len(QUOTES)}건 검증 / 전체 {'통과' if all_ok else '실패 있음'}")


if __name__ == "__main__":
    main()
