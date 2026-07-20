#!/usr/bin/env python3
"""
str03_consistency_analyze.py — STR-03 자기일관성(self-consistency) 분석

방법: 같은 100건(sample_100_for_meeting.csv)을 동일 프롬프트(v3)로 temperature=0.4에서
3회 독립 실행한 결과(str03_consistency_run{1,2,3}.jsonl)를 ODINO로 매칭해, 값이 딱
떨어지는 5개 필드(part_category, severity, driving_context, insufficient_info,
mentions_existing_recall)가 3회 실행에서 얼마나 일치하는지 계산한다.

다른 LLM이나 사람 라벨과 "비교해서 정답을 정하는" 방식이 아니라, 같은 모델이 스스로
얼마나 안정적으로 판단하는지를 재는 것 — 3회 다 갈리는 레코드일수록 모델 자신도 헷갈리는
애매한 케이스라는 뜻이고, 그런 레코드일수록 사람 검토 우선순위가 높다는 전제.

evidence_quote·symptoms(자유 서술)는 문자열 정확일치 비교가 무의미해 5개 비교 대상에서는
빠졌지만, 이번에 "의미가 맞다/틀리다"를 판정하지 않는 순수 기계적 보조지표를 추가했다:
  - evidence_quote: 원문(CDESCR) 안에서 인용한 위치(글자 단위 span)가 3회 간 얼마나
    겹치는지(IoU, Intersection over Union). 겹침이 높으면 "같은 근거를 보고도 판단이
    갈렸다"는 뜻(=규칙 자체가 애매), 겹침이 낮으면 "각기 다른 단서를 근거로 삼았다"는
    뜻(=원문 자체에 애매한 단서가 여럿)이라 해석이 달라진다.
  - symptoms: 3회 증상 명사구를 공백 기준 단어 집합으로 보고 자카드 유사도 평균.
    같은 뜻을 다른 단어로 쓴 경우(paraphrase)는 낮게 나올 수 있다는 한계를 리포트에
    명시한다 — 이 값 자체를 정답 판정에 쓰지 않고 참고 지표로만 사용.
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_PATHS = [REPO_ROOT / f"data/processed/str03_consistency_run{i}.jsonl" for i in (1, 2, 3)]
INPUT_CSV = REPO_ROOT / "data/samples/sample_100_for_meeting.csv"
OUT_REPORT = REPO_ROOT / "data/processed/str03_consistency_report.md"
OUT_CSV = REPO_ROOT / "data/processed/str03_consistency_detail.csv"

DISCRETE_FIELDS = ["part_category", "severity", "driving_context",
                    "insufficient_info", "mentions_existing_recall"]
FIELD_LABEL = {
    "part_category": "부품 분류", "severity": "심각도", "driving_context": "주행 상황",
    "insufficient_info": "정보부족 여부", "mentions_existing_recall": "기존리콜 언급 여부",
}


def fix_mojibake(text: str) -> str:
    if not isinstance(text, str):
        return ""
    if "â" in text or "Ã" in text:
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


def load_runs():
    runs = []
    for path in RUN_PATHS:
        if not path.exists():
            sys.exit(f"실행 결과 없음: {path} — 먼저 3회 실행을 완료하세요.")
        recs = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                recs[str(r["odino"])] = r
        runs.append(recs)
    return runs


def load_cdescr_norm():
    with open(INPUT_CSV, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return {str(r["ODINO"]): normalize_text(fix_mojibake(r["CDESCR"])) for r in rows}


def quote_span(quote: str, cdescr_norm: str):
    """정규화된 원문 안에서 인용문의 (시작,끝) 글자 위치. 못 찾으면 None."""
    q = normalize_text(quote)
    if not q or not cdescr_norm:
        return None
    idx = cdescr_norm.find(q)
    if idx != -1:
        return (idx, idx + len(q))
    if len(q) >= 20:  # str01_batch_structurize.py의 check_quote와 동일한 부분매칭 허용
        idx = cdescr_norm.find(q[:20])
        if idx != -1:
            return (idx, idx + 20)
    return None


def pairwise_mean(items, fn):
    """3개(run1,run2,run3) 중 실제 존재하는 쌍에 대해 fn(a,b) 평균."""
    vals = [x for x in items if x is not None]
    pairs = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i] is not None and items[j] is not None:
                pairs.append(fn(items[i], items[j]))
    return sum(pairs) / len(pairs) if pairs else None


def span_iou(s1, s2):
    inter = max(0, min(s1[1], s2[1]) - max(s1[0], s2[0]))
    union = max(s1[1], s2[1]) - min(s1[0], s2[0])
    return inter / union if union > 0 else 1.0


def word_set(symptoms_list):
    words = set()
    for phrase in (symptoms_list or []):
        words |= set(str(phrase).split())
    return words


def jaccard(a, b):
    u = a | b
    return len(a & b) / len(u) if u else 1.0


def tier(score):
    if score == 0:
        return "안정"
    if score <= 2:
        return "부분 흔들림"
    return "불안정"


def main():
    runs = load_runs()
    cdescr_map = load_cdescr_norm()
    common_ids = sorted(set(runs[0]) & set(runs[1]) & set(runs[2]), key=int)
    missing = (set(runs[0]) | set(runs[1]) | set(runs[2])) - set(common_ids)
    if missing:
        print(f"경고: 3회 전부에 존재하지 않는 ODINO {len(missing)}건 제외: {sorted(missing)}")

    per_field_hist = {f: Counter() for f in DISCRETE_FIELDS}  # unique값 개수(1/2/3) 분포
    details = []

    for odino in common_ids:
        recs = [runs[k][odino] for k in range(3)]
        field_unique = {}
        field_values = {}
        for f in DISCRETE_FIELDS:
            vals = [r.get(f) for r in recs]
            n_unique = len(set(vals))
            field_unique[f] = n_unique
            field_values[f] = vals
            per_field_hist[f][n_unique] += 1
        instability = sum(1 for f in DISCRETE_FIELDS if field_unique[f] > 1)

        cdescr_norm = cdescr_map.get(odino, "")
        spans = [quote_span(r.get("evidence_quote", ""), cdescr_norm) for r in recs]
        evidence_overlap = pairwise_mean(spans, span_iou)

        sym_sets = [word_set(r.get("symptoms")) for r in recs]
        symptom_overlap = pairwise_mean(sym_sets, jaccard)

        details.append({
            "odino": odino,
            "instability_score": instability,
            "tier": tier(instability),
            **{f: "/".join(str(v) for v in field_values[f]) for f in DISCRETE_FIELDS},
            "evidence_overlap_iou": round(evidence_overlap, 3) if evidence_overlap is not None else "",
            "symptom_overlap_jaccard": round(symptom_overlap, 3) if symptom_overlap is not None else "",
        })

    n = len(details)
    tier_counts = Counter(d["tier"] for d in details)
    score_hist = Counter(d["instability_score"] for d in details)

    # 상관 분석용: instability 유무에 따른 evidence_overlap 평균
    def mean_overlap(subset, key):
        vals = [d[key] for d in subset if d[key] != ""]
        return sum(vals) / len(vals) if vals else None

    stable = [d for d in details if d["instability_score"] == 0]
    unstable = [d for d in details if d["instability_score"] > 0]
    severity_disagree = [d for d in details if len(set(d["severity"].split("/"))) > 1]
    severity_agree = [d for d in details if len(set(d["severity"].split("/"))) == 1]

    # CSV 저장
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["odino", "instability_score", "tier"] + DISCRETE_FIELDS
                            + ["evidence_overlap_iou", "symptom_overlap_jaccard"])
        w.writeheader()
        for d in sorted(details, key=lambda x: (-x["instability_score"],
                                                  x["evidence_overlap_iou"] if x["evidence_overlap_iou"] != "" else 1)):
            w.writerow(d)

    # 리포트 저장
    lines = []
    lines.append("# STR-03 자기일관성(Self-Consistency) 분석 리포트\n")
    lines.append("## 개요")
    lines.append(f"- 대상: {n}건 (동일 100건을 v3 프롬프트, temperature=0.4로 3회 독립 실행)")
    lines.append("- 목적: 다른 LLM·사람 라벨과 비교하는 게 아니라, 같은 모델이 스스로 얼마나 "
                 "일관되게 판단하는지 측정 — 흔들리는 레코드 = 사람 검토 우선순위")
    lines.append(f"- 산출물: `{OUT_CSV.relative_to(REPO_ROOT)}` (전 건 상세), 이 리포트\n")

    lines.append("## 필드별 3회 일치율 (정형값 5개)")
    lines.append("| 필드 | 3/3 일치(안정) | 2/1 (부분흔들림) | 1/1/1 (완전분열) |")
    lines.append("|---|---|---|---|")
    for f in DISCRETE_FIELDS:
        h = per_field_hist[f]
        lines.append(f"| {FIELD_LABEL[f]} ({f}) | {h.get(1,0)} ({h.get(1,0)/n:.1%}) | "
                     f"{h.get(2,0)} ({h.get(2,0)/n:.1%}) | {h.get(3,0)} ({h.get(3,0)/n:.1%}) |")
    lines.append("")

    lines.append("## 레코드별 불안정 점수 분포 (5개 필드 중 일치하지 않는 필드 수)")
    lines.append("| 불안정 점수 | 건수 |")
    lines.append("|---|---|")
    for s in range(6):
        lines.append(f"| {s} | {score_hist.get(s,0)} |")
    lines.append("")
    lines.append("| 등급 | 건수 | 비율 |")
    lines.append("|---|---|---|")
    for t in ["안정", "부분 흔들림", "불안정"]:
        c = tier_counts.get(t, 0)
        lines.append(f"| {t} | {c} | {c/n:.1%} |")
    lines.append("")

    lines.append("## 보조지표 — evidence_quote 위치 겹침(IoU) / symptoms 단어 자카드")
    ev_stable = mean_overlap(stable, "evidence_overlap_iou")
    ev_unstable = mean_overlap(unstable, "evidence_overlap_iou")
    sy_stable = mean_overlap(stable, "symptom_overlap_jaccard")
    sy_unstable = mean_overlap(unstable, "symptom_overlap_jaccard")
    lines.append(f"- 안정 레코드(5필드 전부 일치, n={len(stable)}) 평균 evidence 겹침(IoU): "
                 f"{ev_stable:.3f}" if ev_stable is not None else "- 안정 레코드 evidence 겹침: 데이터 없음")
    lines.append(f"- 불안정 레코드(1개 이상 필드 흔들림, n={len(unstable)}) 평균 evidence 겹침(IoU): "
                 f"{ev_unstable:.3f}" if ev_unstable is not None else "- 불안정 레코드 evidence 겹침: 데이터 없음")
    lines.append(f"- 안정 레코드 평균 symptom 자카드: {sy_stable:.3f}" if sy_stable is not None else "")
    lines.append(f"- 불안정 레코드 평균 symptom 자카드: {sy_unstable:.3f}" if sy_unstable is not None else "")
    lines.append("")
    lines.append(f"- severity 3회 불일치 레코드(n={len(severity_disagree)}) 평균 evidence 겹침(IoU): "
                 f"{mean_overlap(severity_disagree, 'evidence_overlap_iou'):.3f}"
                 if mean_overlap(severity_disagree, 'evidence_overlap_iou') is not None else "- severity 불일치 evidence 겹침: 데이터 없음")
    lines.append(f"- severity 3회 일치 레코드(n={len(severity_agree)}) 평균 evidence 겹침(IoU): "
                 f"{mean_overlap(severity_agree, 'evidence_overlap_iou'):.3f}"
                 if mean_overlap(severity_agree, 'evidence_overlap_iou') is not None else "- severity 일치 evidence 겹침: 데이터 없음")
    lines.append("")
    lines.append("> 해석 가이드: evidence 겹침이 높은데도 판단이 갈렸다면 '같은 근거를 보고도 "
                 "규칙 적용이 흔들린 것'(프롬프트 규칙이 모호할 가능성), 겹침이 낮다면 '애초에 "
                 "다른 단서를 근거로 삼은 것'(원문 자체가 여러 단서를 담고 있어 모델이 어느 것을 "
                 "볼지부터 흔들린 것)으로 구분해서 읽는다.\n")

    lines.append("## temperature와 결과의 관계 — 해석상 반드시 짚어야 할 점")
    lines.append("이 실험에서 관측된 흔들림(불안정 34건, 필드별 85~99% 일치)은 **전부 "
                 "temperature=0.4로 일부러 올린 결과다.** 이건 숨은 결함이 아니라 self-consistency "
                 "진단 방법 자체의 설계 원리 — \"살짝 흔들어서 어느 판단이 약한 다리인지 본다\"는 "
                 "것이라, 흔들림이 온도 때문에 발생하는 것 자체는 의도된 동작이다. 다만 이로 인해 "
                 "이 데이터로 정당하게 주장할 수 있는 것과 없는 것이 갈린다.\n")
    lines.append("- **정당한 주장 — 상대적 순위**: 66건이 T=0.4에서도 5필드 전부 그대로라면, 이 "
                 "레코드들은 모델이 강하게 확신하는 케이스다. 반대로 상위 34건은 온도를 얼마로 "
                 "잡든(0.2든 0.6이든) 상대적으로 더 흔들릴 가능성이 높은 후보군 — 이 순위를 "
                 "\"사람이 먼저 봐야 할 우선순위\"로 쓰는 것은 타당하다.")
    lines.append("- **부당한 주장 — 절대 수치**: \"부품분류 85% 일치·심각도 87% 일치\"를 \"Gemini "
                 "운영(temperature=0) 판정이 이 정도로 불안정하다\"고 읽으면 안 된다. T를 더 "
                 "올렸으면 이 숫자는 더 나빠졌을 것이고, 이는 모델의 실제 신뢰도가 아니라 이번에 "
                 "고른 T=0.4라는 진단 강도를 반영하는 수치다. 이 실험은 T=0(운영값) 3회 반복이라는 "
                 "대조군 없이 진행됐다 — 즉 \"T=0 대비 얼마나 더 흔들렸는가\"는 이 리포트가 답할 수 "
                 "없는 질문이며, 정확한 정량화가 필요하면 별도로 T=0 대조군 실행이 필요하다.")
    lines.append("- **작은 표본 주의**: \"severity 불일치 13건의 evidence 겹침(0.882)이 일치 87건"
                 "(0.801)보다 오히려 높다\"는 위 상관관계는 n=13이라는 작은 표본에서 나온 관찰이다. "
                 "이게 \"심각도 판정 규칙이 실제로 모호하다\"는 확정된 결론이 아니라, **추가 검증이 "
                 "필요한 가설**로 취급해야 한다 — 반복 횟수를 늘리거나(3회→5회 이상) 여러 temperature "
                 "값에서 같은 방향의 패턴이 재현되는지 확인하기 전까지는.")
    lines.append("- **결론**: 이번 실험의 확실한 산출물은 \"이 100건 중 어디를 먼저 사람이 봐야 "
                 "하는가\"라는 우선순위 리스트(위 표)이고, 절대 수치나 필드 간 상관관계 해석은 "
                 "참고 가설로만 취급한다.\n")

    lines.append("## 검토 우선순위 상위 레코드 (불안정 점수 높은 순)")
    top = sorted(details, key=lambda d: (-d["instability_score"],
                                          d["evidence_overlap_iou"] if d["evidence_overlap_iou"] != "" else 1))[:15]
    lines.append("| ODINO | 점수 | 등급 | part_category(3회) | severity(3회) | driving_context(3회) | "
                 "insufficient_info(3회) | mentions_existing_recall(3회) | evidence IoU | symptom 자카드 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for d in top:
        lines.append(f"| {d['odino']} | {d['instability_score']} | {d['tier']} | {d['part_category']} | "
                     f"{d['severity']} | {d['driving_context']} | {d['insufficient_info']} | "
                     f"{d['mentions_existing_recall']} | {d['evidence_overlap_iou']} | {d['symptom_overlap_jaccard']} |")
    lines.append("")

    lines.append("## 한계")
    lines.append("- temperature=0.4는 운영 파이프라인(0)과 다른 진단 전용 설정 — 이 결과로 "
                 "운영 출력 자체를 바꾸지 않는다. (자세한 해석 범위는 위 'temperature와 결과의 "
                 "관계' 절 참조)")
    lines.append("- symptom 자카드는 공백 기준 단어 집합 비교라 같은 뜻을 다른 단어로 쓴 "
                 "경우(예: '제동 밀림' vs '브레이크 밀리는 느낌')는 실제보다 낮게 나올 수 있음 — "
                 "정답 판정이 아니라 참고 지표로만 사용.")
    lines.append("- evidence_quote 위치를 못 찾은 건(원문 부분매칭 실패)은 겹침 계산에서 제외됨.")
    lines.append("- 이 분석은 '어느 값이 정답인가'를 정하지 않는다 — 오직 '어디를 사람이 먼저 "
                 "봐야 하는가'의 우선순위만 제공한다.\n")

    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"완료: {n}건 분석")
    print(f"등급 분포: {dict(tier_counts)}")
    print(f"리포트: {OUT_REPORT}")
    print(f"상세 CSV: {OUT_CSV}")


if __name__ == "__main__":
    main()
