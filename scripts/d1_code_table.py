"""1일차: payment_terms_raw 표기 → 표준 코드 7종 매핑표 만들기 (원본은 읽기만 한다)

실행: uv run python scripts/d1_code_table.py
결과: workbench/day1/outputs/d1_code_table.csv (utf-8-sig)
판단은 표기 속 단어로만 한다. 단어로 정할 수 없으면 '검토 필요'.
"""
import re
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

SRC = "data/day1/d1_buyers_raw.xlsx"
DICT = "data/data_dictionary.xlsx"
OUT = "workbench/day1/outputs/d1_code_table.csv"
REVIEW = "검토 필요"


def classify(raw):
    """(표준 코드, 판단 근거, 확신)을 돌려준다. t = TRIM · UPPER 한 값."""
    t = raw.strip().upper()
    days = re.search(r"(\d+)\s?(DAYS?|D)\b|\b(\d+)$|[A-Z/](\d+)", t)
    n = next((g for g in (days.groups() if days else []) if g and g.isdigit()), None)

    # 1) 선수 비율이 붙은 분할 송금
    if re.search(r"\d+%", t) and "ADVANCE" in t:
        if re.search(r"30%.*ADVANCE.*70%", t):
            return "TT_SPLIT_30_70", "'30% T/T advance' + '70% within 30 days after B/L'", "높음"
        return REVIEW, "'10% advance + 90% O/A' — 선수 비율이 30/70이 아니라 7종 어디에도 맞지 않음", "낮음"
    if re.search(r"T/?T 30[/:]70", t):
        return "TT_SPLIT_30_70", "'T/T' + '30/70' 비율 — 잔금 시점은 표기에 없음", "높음"

    # 2) 선수금
    if "IN ADVANCE" in t or "BEFORE SHIPMENT" in t or "ADVANCE" in t:
        word = next(w for w in ("BEFORE SHIPMENT", "IN ADVANCE", "ADVANCE") if w in t)
        return "TT_ADV", f"'{word}' (선적 전 송금)", "높음"

    # 3) 신용장
    if re.search(r"\bL/?C\b", t) or "신용장" in raw:
        if "SIGHT" in t or "일람불" in raw:
            word = "일람불" if "일람불" in raw else "at sight"
            return "LC_SIGHT", f"'L/C' + '{word}'".replace("'L/C'", "'신용장'") if "신용장" in raw \
                else f"'L/C' + '{word}'", "높음"
        if "USANCE" in t:
            return "LC_USANCE", f"'L/C' + 'usance' + {n}일", "높음"
        if n:
            return "LC_USANCE", f"'L/C' + '{n} days' (기한 있는 신용장 = 기한부)", "높음"
        return REVIEW, "'L/C'만 있고 일람/기한 표시 없음", "낮음"

    # 4) 추심
    if re.search(r"\bD/?P\b", t):
        return "DP", "'D/P' (Documents against Payment)" + (" + 'sight'" if "SIGHT" in t else ""), "높음"
    if re.search(r"^D/?A\s?\d|\bD/A\b|DOCUMENTS AGAINST ACCEPTANCE", t):
        word = "Documents against acceptance" if "DOCUMENTS" in t else "D/A"
        return "DA", f"'{word}' + {n}일", "높음"

    # 5) 사후송금
    if re.search(r"\bO/?A\s?\d|\bO/A\b|OPEN (ACCOUNT|ACCT)", t):
        word = re.search(r"O/?A|OPEN (ACCOUNT|ACCT)", t).group(0)
        return "OA", f"'{word}' (Open Account) + {n}일", "높음"
    if t.startswith("NET"):
        return "OA", f"'Net {n}' (외상 기간 조건)", "높음"

    # 6) T/T + 기간
    if re.search(r"\bT/?T\b", t):
        if "AFTER B/L" in t:
            return "OA", f"'T/T' + '{n} days after B/L' (선적 후 송금)", "높음"
        if n:
            return "OA", f"'T/T' + '{n}days' — 'after'가 없어 기산점 불명. 기간이 있어 사후송금으로 봄", "낮음"
        return REVIEW, "'T/T'(송금)만 있고 시점(선적 전/후) 단어 없음", "낮음"

    return REVIEW, "규칙에 맞는 단어 없음", "낮음"


df = pd.read_excel(SRC, sheet_name="buyers", dtype=object)
variants = df["payment_terms_raw"].value_counts(sort=False)
rows = []
for raw in sorted(variants.index, key=lambda s: (s.strip().upper(), s)):
    code, why, conf = classify(raw)
    note = []
    if raw != raw.strip():
        note.append("앞뒤 공백 있음")
    if raw == raw.lower() and raw != raw.upper():
        note.append("소문자")
    if note:
        why += f" [{', '.join(note)}]"
    rows.append({"원래 표기": raw, "표준 코드": code, "판단 근거(어느 단어로)": why, "확신(높음/낮음)": conf})
table = pd.DataFrame(rows)
table.to_csv(OUT, index=False, encoding="utf-8-sig")

print(f"표기 {len(table)}종 → {OUT}")
print(table["표준 코드"].value_counts().to_string(), "\n")
print("확신:", table["확신(높음/낮음)"].value_counts().to_dict())
cnt = df["payment_terms_raw"].map(lambda r: classify(r)[0]).value_counts()
print("행(153) 기준 코드별:", cnt.to_dict(), "\n")

# 과정 코드표(TRIM·UPPER 키)와 대조 — 내 판단을 바꾸지 않고 차이만 보인다
pm = pd.read_excel(DICT, sheet_name="payment_terms_map", header=2)
ref = dict(zip(pm["raw_upper"].astype(str).str.strip(), pm["payment_method"]))
table["key"] = table["원래 표기"].str.strip().str.upper()
table["과정 코드표"] = table["key"].map(ref).fillna("(없음)")
diff = table[(table["과정 코드표"] != "(없음)") & (table["과정 코드표"] != table["표준 코드"])]
print("과정 코드표와 다른 판단:")
print(diff[["원래 표기", "표준 코드", "과정 코드표"]].to_string(index=False))
print("\n과정 코드표에 없는 표기:")
print(table[table["과정 코드표"] == "(없음)"][["원래 표기", "표준 코드"]].to_string(index=False))
