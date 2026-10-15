"""2일차: buyers 시트 정제 — workbench/day2/rules/정제규칙.md 1–7칸을 그대로 옮긴다.

실행: uv run python scripts/clean_buyers.py
입력(읽기만): data/checkpoints/d2_start.xlsx (buyers · fx_at_ref) · workbench/day2/data/fx_krw_daily.csv
출력: workbench/day2/outputs/d2_buyers_clean.csv (150행) · workbench/day2/outputs/dq_report.md (전·후 비교)
"""
import re
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

SRC = "data/checkpoints/d2_start.xlsx"
FX_DAILY = "workbench/day2/data/fx_krw_daily.csv"
OUT_CSV = "workbench/day2/outputs/d2_buyers_clean.csv"
OUT_MD = "workbench/day2/outputs/dq_report.md"
ASOF = pd.Timestamp("2026-08-31")
LAG_END, LAG_START = pd.Timestamp("2026-07-31"), pd.Timestamp("2026-07-01")  # 기준일 30일 전 시점의 30일 창

BUCKETS = ["ar_current", "ar_1_30", "ar_31_60", "ar_61_90", "ar_91p"]
AMOUNT_COLS = ["ar_balance"] + BUCKETS
FIN_COLS = ["current_assets", "current_liabilities", "total_liabilities", "equity",
            "accounts_receivable", "revenue", "operating_income"]
FIN_FLAG_COLS = ["current_assets", "current_liabilities", "total_liabilities", "equity", "revenue"]
TXN_COLS = ["avg_days_late_12m", "avg_dpd_last3m", "avg_dpd_prev3m"]
OUT_COLS = ["buyer_id", "payment_method", "ccy_clean", "amt_num", "ar_balance_usd",
            "pct_current", "pct_ar_31p", "pct_91plus", "max_dpd", "avg_days_late", "late_ratio",
            "dpd_trend", "dispute_ratio", "current_ratio", "debt_to_equity", "dso_buyer", "op_margin",
            "fin_missing", "neg_equity", "country_risk", "crc_unclassified", "unit_flag",
            "fx_chg_30d", "fx_chg_30d_lag30", "late_30d"]

# 1칸 통화: TRIM · UPPER 후 대응표
CCY_MAP = {"USD": "USD", "US$": "USD", "EUR": "EUR", "EURO": "EUR",
           "CNY": "CNY", "RMB": "CNY", "JPY": "JPY", "YEN": "JPY"}
# fx 표의 통화 이름 · 1단위당 나눌 값(JPY는 100엔당 원화)
FX_KEY = {"USD": ("USD", 1), "EUR": ("EUR", 1), "CNY": ("CNY", 1), "JPY": ("JPY100", 100)}
DAILY_COL = {"USD": "usd_krw", "EUR": "eur_krw", "CNY": "cny_krw", "JPY": "jpy100_krw"}


def md(frame):
    """tabulate 없이 Markdown 표로 바꾼다."""
    cols = [str(c) for c in frame.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in frame.itertuples(index=False):
        lines.append("| " + " | ".join(str(v).replace("|", "\\|") for v in row) + " |")
    return "\n".join(lines)


def to_number(v):
    """2칸 숫자 변환: 공백 · 쉼표 · 앞뒤 통화 문자 제거, 끝의 k는 ×1,000. 못 바꾸면 멈춘다."""
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    s = re.sub(r"^[A-Za-z]{3}\s*|\s*[A-Za-z]{3}$", "", s).strip()
    mult = 1
    if s.lower().endswith("k"):
        s, mult = s[:-1], 1000
    try:
        return float(s) * mult
    except ValueError:
        raise ValueError(f"숫자로 바꿀 수 없는 값: {v!r}") from None


def safe_div(a, b):
    a, b = pd.to_numeric(a).astype(float), pd.to_numeric(b).astype(float)
    return (a / b.where(b != 0))


raw = pd.read_excel(SRC, sheet_name="buyers", dtype=object)
fx_ref = pd.read_excel(SRC, sheet_name="fx_at_ref")
fx_daily = pd.read_csv(FX_DAILY, parse_dates=["date"]).set_index("date").sort_index()
assert len(raw) == 150 and raw["buyer_id"].is_unique
df = raw.copy()
row_no = df.index + 2  # 엑셀 행 번호

# ---------- 1칸 통화 ----------
df["ccy_clean"] = df["currency"].str.strip().str.upper().map(CCY_MAP)
assert df["ccy_clean"].notna().all(), df.loc[df["ccy_clean"].isna(), "currency"].unique()

# ---------- 2칸 숫자 변환 ----------
for c in AMOUNT_COLS:
    df[c] = df[c].map(to_number)
df["amt_num"] = df["ar_balance"]  # 변환만 한 값(4칸 보정 전)

# ---------- 7칸 환율(기준일 2026-08-31) ----------
fx_asof = fx_ref[pd.to_datetime(fx_ref["ref_date"]) == ASOF].set_index("ccy")
usd_krw = fx_asof.loc["USD", "krw_close"]
to_usd = df["ccy_clean"].map(lambda c: fx_asof.loc[FX_KEY[c][0], "krw_close"] / FX_KEY[c][1] / usd_krw)
df["fx_chg_30d"] = df["ccy_clean"].map(lambda c: fx_asof.loc[FX_KEY[c][0], "chg_30d"])


def close_on_or_before(day, col):
    """그날이 휴일이면 직전 관측일 값."""
    return fx_daily.loc[:day, col].iloc[-1]


lag = {c: close_on_or_before(LAG_END, col) / close_on_or_before(LAG_START, col) - 1
       for c, col in DAILY_COL.items()}
df["fx_chg_30d_lag30"] = df["ccy_clean"].map(lag)
# 검산: 일별 파일로 계산한 기준일 30일 변화가 fx_at_ref의 chg_30d와 같아야 시차 계산 방식이 맞다
for c, col in DAILY_COL.items():
    chk = close_on_or_before(ASOF, col) / close_on_or_before(ASOF - pd.Timedelta(days=30), col) - 1
    assert abs(chk - fx_asof.loc[FX_KEY[c][0], "chg_30d"]) < 1e-4, (c, chk)

# ---------- 4칸 단위 의심 ----------
bucket_sum = df[BUCKETS].sum(axis=1)
df["unit_flag"] = (df["amt_num"] * to_usd > df["credit_limit_usd"] * 10).astype(int)
mismatch = (df["amt_num"] - bucket_sum).abs() > 0.5
df["ar_fixed"] = df["amt_num"].where(~mismatch, bucket_sum)
df["ar_balance_usd"] = (df["ar_fixed"] * to_usd).round(2)

# 잔액 구성비(잔액 0이면 연체 비중 0, 미연체 비중 1)
df["pct_current"] = safe_div(df["ar_current"], bucket_sum).fillna(1.0)
df["pct_ar_31p"] = safe_div(df[["ar_31_60", "ar_61_90", "ar_91p"]].sum(axis=1), bucket_sum).fillna(0.0)
df["pct_91plus"] = safe_div(df["ar_91p"], bucket_sum).fillna(0.0)

# ---------- 3칸 결측: 플래그 먼저, 그다음 중위수 ----------
for c in FIN_COLS + TXN_COLS:
    df[c] = pd.to_numeric(df[c])
df["fin_missing"] = df[FIN_FLAG_COLS].isna().any(axis=1).astype(int)
equity_raw = df["equity"].copy()  # 5칸 판정은 원값으로
medians = {c: df[c].median() for c in FIN_COLS + TXN_COLS}
df["late_ratio"] = safe_div(df["late_invoices_12m"].astype(float), df["invoices_12m"])
df["dispute_ratio"] = safe_div(df["dispute_cnt_12m"].astype(float), df["invoices_12m"])
for c in ["late_ratio", "dispute_ratio"]:  # 거래 0건이면 비율이 없다 → 같은 규칙(중위수)
    medians[c] = df[c].median()
fill_counts = {c: int(df[c].isna().sum()) for c in medians}
for c, m in medians.items():
    df[c] = df[c].fillna(m)

df["avg_days_late"] = df["avg_days_late_12m"]
df["dpd_trend"] = df["avg_dpd_last3m"] - df["avg_dpd_prev3m"]
df["current_ratio"] = safe_div(df["current_assets"], df["current_liabilities"])
df["dso_buyer"] = safe_div(df["accounts_receivable"], df["revenue"]) * 365
df["op_margin"] = safe_div(df["operating_income"], df["revenue"])

# ---------- 5칸 자본잠식 ----------
df["neg_equity"] = (equity_raw <= 0).astype(int)  # 원값이 빈칸이면 0
df["debt_to_equity"] = safe_div(df["total_liabilities"], df["equity"]).where(df["neg_equity"] == 0)

# ---------- 6칸 국가위험 ----------
df["crc_unclassified"] = (df["oecd_crc"].astype(str).str.strip() == "-").astype(int)
df["country_risk"] = df["oecd_crc"].where(df["crc_unclassified"] == 0, 0).astype(int)

out = df[OUT_COLS].copy()
for c in ["dso_buyer", "dpd_trend", "avg_days_late"]:
    out[c] = out[c].round(2)
for c in ["pct_current", "pct_ar_31p", "pct_91plus", "late_ratio", "dispute_ratio",
          "current_ratio", "debt_to_equity", "op_margin", "fx_chg_30d", "fx_chg_30d_lag30"]:
    out[c] = out[c].round(4)

# ---------- 점검 ----------
assert out.shape == (150, 25) and out.columns[0] == "buyer_id" and out.columns[-1] == "late_30d"
assert out["buyer_id"].is_unique
assert out[["pct_current", "pct_ar_31p", "pct_91plus"]].stack().between(0, 1).all()
nan_left = out.isna().sum()
nan_left = nan_left[nan_left > 0]
assert set(nan_left.index) <= {"debt_to_equity"}, nan_left  # 5칸 규칙으로 남긴 빈칸만 허용

out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

# ---------- 전·후 비교 보고서 ----------
def type_mix(s):
    return ", ".join(f"{k}:{n}" for k, n in s.map(lambda v: type(v).__name__ if pd.notna(v) else "NaN")
                     .value_counts().items())


before_after = pd.DataFrame([
    {"열(원본 → 결과)": "currency → ccy_clean", "전": f"{raw['currency'].nunique()}종 {raw['currency'].value_counts().to_dict()}",
     "후": f"{out['ccy_clean'].nunique()}종 {out['ccy_clean'].value_counts().to_dict()}"},
    {"열(원본 → 결과)": "ar_balance → amt_num", "전": type_mix(raw["ar_balance"]), "후": type_mix(out["amt_num"])},
    *[{"열(원본 → 결과)": f"{c} (중간값)", "전": type_mix(raw[c]), "후": type_mix(df[c])} for c in BUCKETS
      if raw[c].map(lambda v: isinstance(v, str)).any()],
    {"열(원본 → 결과)": "oecd_crc → country_risk", "전": type_mix(raw["oecd_crc"]) + f" ('-' {int(df['crc_unclassified'].sum())}건)",
     "후": type_mix(out["country_risk"]) + f" (범위 {out['country_risk'].min()}~{out['country_risk'].max()})"},
])

str_cells = [{"엑셀 행": r, "buyer_id": b, "열": c, "원값": repr(v), "변환값": df.at[i, c]}
             for c in AMOUNT_COLS for i, (r, b, v) in enumerate(zip(row_no, raw["buyer_id"], raw[c]))
             if isinstance(v, str)]
unit_rows = df[mismatch | (df["unit_flag"] == 1)]
unit_tbl = pd.DataFrame({"엑셀 행": row_no[unit_rows.index], "buyer_id": unit_rows["buyer_id"],
                         "ccy": unit_rows["ccy_clean"], "amt_num": unit_rows["amt_num"],
                         "버킷 합": bucket_sum[unit_rows.index], "보정값": unit_rows["ar_fixed"],
                         "ar_balance_usd": unit_rows["ar_balance_usd"], "한도": unit_rows["credit_limit_usd"],
                         "unit_flag": unit_rows["unit_flag"]})
fill_tbl = pd.DataFrame([{"열": c, "원본 결측": int(raw[c].isna().sum()) if c in raw else "–",
                          "채운 칸": fill_counts[c], "중위수": round(m, 4)} for c, m in medians.items()])
neg_tbl = df.loc[df["neg_equity"] == 1, ["buyer_id", "equity", "total_liabilities"]].assign(
    **{"엑셀 행": lambda x: row_no[x.index]})
fx_tbl = pd.DataFrame([{"ccy": c, "USD 환산 계수(×)": round(fx_asof.loc[FX_KEY[c][0], "krw_close"] / FX_KEY[c][1] / usd_krw, 6),
                        "fx_chg_30d": fx_asof.loc[FX_KEY[c][0], "chg_30d"], "fx_chg_30d_lag30": round(lag[c], 4)}
                       for c in FX_KEY])
desc = out.drop(columns=["buyer_id", "payment_method", "ccy_clean"]).describe().T[["count", "mean", "min", "50%", "max"]]
desc = desc.round(4).reset_index().rename(columns={"index": "열"})

report = f"""# buyers 정제 전·후 비교 (dq_report)

- 원본(읽기만): `{SRC}` 시트 buyers · {raw.shape[0]}행 × {raw.shape[1]}열
- 결과: `{OUT_CSV}` · {out.shape[0]}행 × {out.shape[1]}열 (buyer_id 첫 열 · late_30d 마지막 열)
- 규칙: `workbench/day2/rules/정제규칙.md` 1–7칸 · 코드: `scripts/clean_buyers.py`
- 기준일 {ASOF.date()} · 환율 `fx_at_ref` 같은 날 행 · 시차 환율 `{FX_DAILY}`

## 1. 표기 · 타입 (1·2·6칸)
{md(before_after)}

## 2. 글자 → 숫자 변환 {len(str_cells)}건 (2칸)
{md(pd.DataFrame(str_cells))}

## 3. 단위 의심 · 잔액 보정 (4칸)
`unit_flag` = amt_num × USD 환산 계수 > credit_limit_usd × 10. amt_num ≠ 버킷 합이면 버킷 합으로 보정한 뒤 USD 환산한다.
{md(unit_tbl)}

## 4. 결측 채우기 (3칸)
플래그를 먼저 만든 뒤 열별 중위수(채우기 전 150행 값)로 채웠다. `fin_missing` = 유동자산 · 유동부채 · 총부채 · 자기자본 · 매출 중 하나라도 빈칸 → **{int(out['fin_missing'].sum())}행**.
late_ratio · dispute_ratio는 invoices_12m = 0이면 분모가 0이라 같은 규칙(중위수)을 따랐다.
{md(fill_tbl)}

## 5. 자본잠식 (5칸)
원값 equity ≤ 0 → `neg_equity=1`, `debt_to_equity`는 빈칸으로 둔다.
{md(neg_tbl[['엑셀 행', 'buyer_id', 'equity', 'total_liabilities']])}

## 6. 환율 · 시차 (7칸)
USD 환산 계수 = 통화 KRW ÷ USD KRW(JPY는 100엔당 값 ÷ 100). `fx_chg_30d_lag30` = 2026-07-31 종가 ÷ 2026-07-01 종가 − 1.
검산: 일별 파일로 계산한 2026-08-31의 30일 변화(직전 관측일 기준)가 `fx_at_ref`의 chg_30d와 4종 모두 일치(차이 < 0.0001).
{md(fx_tbl)}

## 7. 결과 열 요약
남은 빈칸: {nan_left.to_dict() or '없음'} (5칸 규칙으로 남긴 것뿐)
{md(desc)}

## 8. 계산식
| 열 | 식 |
|---|---|
| pct_current | ar_current ÷ 버킷 합 (잔액 0이면 1) |
| pct_ar_31p | (ar_31_60 + ar_61_90 + ar_91p) ÷ 버킷 합 (잔액 0이면 0) |
| pct_91plus | ar_91p ÷ 버킷 합 (잔액 0이면 0) |
| avg_days_late | avg_days_late_12m (중위수 채움) |
| late_ratio | late_invoices_12m ÷ invoices_12m |
| dpd_trend | avg_dpd_last3m − avg_dpd_prev3m (각각 중위수 채움 후) |
| dispute_ratio | dispute_cnt_12m ÷ invoices_12m |
| current_ratio | current_assets ÷ current_liabilities |
| debt_to_equity | total_liabilities ÷ equity (neg_equity=1이면 빈칸) |
| dso_buyer | accounts_receivable ÷ revenue × 365 |
| op_margin | operating_income ÷ revenue |

## 9. 확인 필요
- B029 소수(ar_balance 60,187.68 · ar_31_60 21,007.68)는 규칙대로 그대로 두었다. 센트인지 오류인지 근거 없음.
- 4칸: B141은 보정했지만 한도 × 10 기준에는 걸리지 않아 unit_flag = 0이다. 보정 행 전부에 플래그를 달지는 규칙에서 정해야 한다.
- 결측 플래그 `{{열}}_missing`(거래 3열)은 결과 열 목록에 없어 CSV에 넣지 않았다.
- 중위수는 150행 전체로 구했다. 3일차에 학습·검증을 나누면 학습 데이터만으로 다시 구해야 하는지 확인 필요.
"""
with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write(report)

print(f"저장: {OUT_CSV} {out.shape} · {OUT_MD}")
print("남은 빈칸:", nan_left.to_dict())
print("unit_flag:", int(out["unit_flag"].sum()), "· neg_equity:", int(out["neg_equity"].sum()),
      "· fin_missing:", int(out["fin_missing"].sum()), "· crc_unclassified:", int(out["crc_unclassified"].sum()))
