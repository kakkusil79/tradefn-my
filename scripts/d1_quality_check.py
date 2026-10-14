"""1일차: d1_buyers_raw.xlsx 품질 진단 (읽기 전용 — 값을 고치지 않는다)

실행: uv run python scripts/d1_quality_check.py
결과는 화면(Markdown 표)으로만 출력한다. 보고서 원고: workbench/day1/outputs/d1_quality_report.md
"""
import re
import sys
from collections import Counter

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

SRC = "data/day1/d1_buyers_raw.xlsx"
DICT = "data/data_dictionary.xlsx"
REF_DATE = pd.Timestamp("2026-09-30")  # readme 기준일

df = pd.read_excel(SRC, sheet_name="buyers", dtype=object)
df.insert(0, "_row", df.index + 2)  # 엑셀 행 번호(1행 = 머리글)

NUMERIC_COLS = [
    "ar_balance", "max_dpd_days", "overdue_amount", "pay_score", "oecd_crc",
    "revenue_usd_fy2025", "current_ratio_fy2025", "debt_to_equity_fy2025",
    "dso_fy2025", "op_margin_fy2025",
]


def is_missing(v):
    return v is None or (isinstance(v, float) and pd.isna(v))


def is_blank_text(v):
    return isinstance(v, str) and v.strip() == ""


def md(frame):
    """tabulate 없이 Markdown 표로 바꾼다."""
    cols = [str(c) for c in frame.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in frame.itertuples(index=False):
        lines.append("| " + " | ".join(str(v).replace("|", "\\|") for v in row) + " |")
    return "\n".join(lines)


print(f"# 원본: {SRC} · 시트 buyers · {len(df)}행 × {len(df.columns) - 1}열\n")

# ---------- 1) 열별 유형 · 결측 ----------
rows = []
for c in df.columns[1:]:
    types = Counter(type(v).__name__ for v in df[c] if not is_missing(v))
    rows.append({
        "열": c,
        "파이썬 유형(값 수)": ", ".join(f"{k}:{n}" for k, n in types.most_common()),
        "결측(NaN)": sum(is_missing(v) for v in df[c]),
        "빈 문자열": sum(is_blank_text(v) for v in df[c]),
        "앞뒤 공백": sum(isinstance(v, str) and v != v.strip() for v in df[c]),
        "고유값": df[c].nunique(dropna=True),
    })
print("## 1. 열별 유형 · 결측\n")
print(md(pd.DataFrame(rows)), "\n")

# ---------- 2) 중복 ----------
print("## 2. 중복\n")
full_dup = df.drop(columns="_row").duplicated(keep=False)
print(f"- 모든 열이 같은 행(완전 중복): {int(full_dup.sum())}행")
id_dup = df[df.duplicated("buyer_id", keep=False)].sort_values(["buyer_id", "_row"])
print(f"- buyer_id 중복: {id_dup['buyer_id'].nunique()}개 ID, {len(id_dup)}행\n")
for bid, g in id_dup.groupby("buyer_id"):
    diff = [c for c in df.columns[1:] if g[c].astype(str).nunique() > 1]
    print(f"  - {bid}: 엑셀 행 {g['_row'].tolist()} · 값이 다른 열 = {diff or '없음(완전 중복)'}")
    for c in diff:
        print(f"      {c}: {g[c].tolist()}")
name_dup = df[df.duplicated("buyer_name", keep=False)]
other = name_dup[~name_dup["buyer_id"].isin(id_dup["buyer_id"])]
print(f"- buyer_name 중복(다른 ID): {len(other)}행 {other[['_row', 'buyer_id', 'buyer_name']].values.tolist()}\n")

# ---------- 3) 숫자 열 안의 글자 ----------
print("## 3. 숫자 열에 들어 있는 글자 값\n")


def pattern_of(s):
    t = s.strip()
    if re.fullmatch(r"-", t):
        return "기호 '-'"
    if re.fullmatch(r"[A-Z$]{1,4}\s?[\d,]+(\.\d+)?", t):
        return "통화 접두 + 천단위 쉼표"
    if re.fullmatch(r"[\d,]+", t):
        return "천단위 쉼표"
    if re.fullmatch(r"[\d.]+\s?[kKmM]", t):
        return "k/M 약식"
    if re.search(r"[만천억]", t):
        return "한글 수사(약 ~)"
    if re.fullmatch(r"\d+\s?(일|days?)", t):
        return "숫자 + 단위"
    return "숫자 아님(문구)"


text_rows = []
for c in NUMERIC_COLS:
    for _, r in df.iterrows():
        v = r[c]
        if isinstance(v, str):
            text_rows.append({"열": c, "엑셀 행": r["_row"], "buyer_id": r["buyer_id"],
                              "원값": repr(v), "패턴": pattern_of(v)})
tf = pd.DataFrame(text_rows)
print(md(tf), "\n")
print(md(tf.groupby(["열", "패턴"]).size().reset_index(name="건수")), "\n")

# 정수 열인데 소수가 있는 값
for c in ["ar_balance", "overdue_amount"]:
    fl = df[[isinstance(v, float) and not pd.isna(v) and v != int(v) for v in df[c]]]
    print(f"- {c} 소수점 값: {fl[['_row', 'buyer_id', c, 'ar_currency']].values.tolist()}")
print()

# ---------- 4) 날짜 형식 ----------
print("## 4. since_date 형식\n")
DATE_PATTERNS = [
    ("YYYY-MM-DD", r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
    ("YYYY.M.D", r"\d{4}\.\d{1,2}\.\d{1,2}", "%Y.%m.%d"),
    ("DD/MM/YYYY 또는 MM/DD/YYYY", r"\d{2}/\d{2}/\d{4}", None),
    ("Mon D YYYY (영문 월)", r"[A-Z][a-z]{2} \d{1,2} \d{4}", "%b %d %Y"),
]
fmt_rows, slash_rows, future = [], [], []
for _, r in df.iterrows():
    v = r["since_date"]
    if not isinstance(v, str):
        fmt_rows.append(("엑셀 날짜/기타 유형:" + type(v).__name__, v))
        continue
    for name, rx, f in DATE_PATTERNS:
        if re.fullmatch(rx, v.strip()):
            fmt_rows.append((name, v))
            if f:
                d = pd.to_datetime(v.strip(), format=f)
                if d > REF_DATE:
                    future.append((r["_row"], r["buyer_id"], v))
            else:
                a, b, y = map(int, v.split("/"))
                slash_rows.append({"엑셀 행": r["_row"], "buyer_id": r["buyer_id"], "원값": v,
                                   "앞자리>12(일이 앞)": a > 12, "뒷자리>12(일이 뒤)": b > 12,
                                   "판별": "일/월 순서 확정" if a > 12 or b > 12 else "모호"})
            break
    else:
        fmt_rows.append(("기타", v))
ff = pd.DataFrame(fmt_rows, columns=["형식", "원값"])
summary = ff.groupby("형식").agg(건수=("원값", "size"),
                                예시=("원값", lambda s: ", ".join(map(str, s.head(3))))).reset_index()
print(md(summary), "\n")
sf = pd.DataFrame(slash_rows)
print("슬래시 형식 판별:", sf["판별"].value_counts().to_dict(),
      "| 앞자리>12:", int(sf["앞자리>12(일이 앞)"].sum()), "| 뒷자리>12:", int(sf["뒷자리>12(일이 뒤)"].sum()))
print("기준일(2026-09-30) 이후 날짜:", future, "\n")

# ---------- 5) 범주 열 표기 ----------
print("## 5. 범주 열 표기 · 정합성\n")
cc = df.groupby("country_code")["country"].agg(lambda s: sorted(set(s)))
print("country_code별 country 표기(2개 이상):")
for k, v in cc.items():
    if len(v) > 1:
        print(f"  {k}: {v}")
rg = df.groupby("country_code")["region"].nunique()
print("country_code별 region 2개 이상:", rg[rg > 1].to_dict())
crc = df.groupby("country_code")["oecd_crc"].agg(lambda s: sorted(set(map(str, s))))
print("country_code별 oecd_crc 2개 이상:", {k: v for k, v in crc.items() if len(v) > 1})
print("ar_currency 값:", df["ar_currency"].value_counts(dropna=False).to_dict())
yen = df[df["ar_currency"].isin(["¥"])][["_row", "buyer_id", "country_code", "ar_balance"]]
print("'¥' 행(엔/위안 구분 필요):", yen.values.tolist())
print("industry 결측 행:", df[df["industry"].isna()][["_row", "buyer_id", "segment", "buyer_type"]].values.tolist())
print("segment × buyer_type:\n", md(pd.crosstab(df["segment"], df["buyer_type"]).reset_index()))
print("segment × industry:\n",
      md(pd.crosstab(df["segment"], df["industry"].fillna("(결측)")).reset_index()), "\n")

# 결제조건: 과정 코드표(TRIM·UPPER 키)에 없는 표기
pm = pd.read_excel(DICT, sheet_name="payment_terms_map", header=2)
keys = set(pm["raw_upper"].astype(str).str.strip())
pt = df["payment_terms_raw"].astype(str)
unmapped = df[~pt.str.strip().str.upper().isin(keys)]
print(f"payment_terms_raw 고유 표기 {df['payment_terms_raw'].nunique()}종 → TRIM·UPPER 후 "
      f"{pt.str.strip().str.upper().nunique()}종")
print(f"코드표에 없는 표기 {len(unmapped)}행:",
      unmapped["payment_terms_raw"].map(repr).value_counts().to_dict(), "\n")

# ---------- 6) 값 범위 · 열 사이 정합성 ----------
print("## 6. 값 범위 · 열 사이 정합성\n")


def num(v):
    return v if isinstance(v, (int, float)) and not pd.isna(v) else None


n = df.assign(ar=df["ar_balance"].map(num), od=df["overdue_amount"].map(num),
              dpd=df["max_dpd_days"].map(num))
print("overdue > ar_balance:", n[(n.od.notna()) & (n.ar.notna()) & (n.od > n.ar)][
    ["_row", "buyer_id", "ar", "od"]].values.tolist())
print("dpd>0 인데 overdue=0:", n[(n.dpd > 0) & (n.od == 0)][["_row", "buyer_id", "dpd", "od"]].values.tolist())
print("dpd=0 인데 overdue>0:", n[(n.dpd == 0) & (n.od > 0)][["_row", "buyer_id", "dpd", "od"]].values.tolist())
print("ar_balance=0 인데 overdue>0:", n[(n.ar == 0) & (n.od > 0)][["_row", "buyer_id", "od"]].values.tolist())
print("max_dpd_days > 90:", n[n.dpd > 90][["_row", "buyer_id", "dpd"]].values.tolist())
ps = df["pay_score"].map(num)
print("pay_score 범위:", ps.min(), "~", ps.max(), "| 50 미만:",
      df[ps < 50][["_row", "buyer_id", "pay_score"]].values.tolist())
de = df["debt_to_equity_fy2025"].map(num)
print("debt_to_equity 음수(자본잠식):", df[de < 0][["_row", "buyer_id", "debt_to_equity_fy2025"]].values.tolist())
cr = df["current_ratio_fy2025"].map(num)
print("current_ratio < 1:", int((cr < 1).sum()), "건")
print("ar_balance 통화별 최대:", n.groupby(df["ar_currency"])["ar"].max().to_dict())

# 재무 요약문 ↔ 숫자 열
fin = ["revenue_usd_fy2025", "current_ratio_fy2025", "debt_to_equity_fy2025", "dso_fy2025", "op_margin_fy2025"]
not_recv = df["fin_summary_text"].astype(str).str.contains("not received")
print("'not received' 문구:", int(not_recv.sum()), "행 · 그중 재무 숫자가 하나라도 있는 행:",
      df[not_recv & df[fin].notna().any(axis=1)][["_row", "buyer_id"]].values.tolist())
print("재무 숫자 5개 모두 빈 행:", int(df[fin].isna().all(axis=1).sum()))
part = df[df["revenue_usd_fy2025"].notna() & df[fin[1:]].isna().any(axis=1)]
print("매출은 있고 비율 일부가 빈 행:", len(part), "· 그중 'not disclosed' 문구 있는 행:",
      int(part["fin_summary_text"].str.contains("not disclosed").sum()))
om = pd.to_numeric(df["op_margin_fy2025"])
print("op_margin 범위:", om.min(), "~", om.max())
usd = df[df["ar_currency"].isin(["USD", "usd", "US$"])]["ar_balance"].map(num).dropna()
print("USD계 ar_balance 상위 3:", usd.sort_values(ascending=False).head(3).tolist(),
      "· 0 초과 중앙값:", usd[usd > 0].median())
print("oecd_crc '-' 국가:", df[df["oecd_crc"] == "-"]["country_code"].value_counts().to_dict())
mm = []
for _, r in df.iterrows():
    m = re.search(r"USD ([\d.]+)M", str(r["fin_summary_text"]))
    rev = num(r["revenue_usd_fy2025"])
    if m and rev is not None and abs(float(m.group(1)) - rev / 1e6) > 0.051:
        mm.append((r["_row"], r["buyer_id"], m.group(0), rev))
    if m and rev is None:
        mm.append((r["_row"], r["buyer_id"], m.group(0), "revenue 빈칸"))
print("요약문 매출 ↔ revenue_usd 불일치:", mm)
