"""3일차 실습 C: hanbit_lunch_log.csv 품질 진단 (읽기 전용 — 값을 고치지 않는다)

실행: uv run python scripts/lunch_quality.py
결과: workbench/day3/outputs/lunch_quality.md
(가상) 한빛정밀(주) 본사 구내식당 '한빛식당'의 가상 점심 기록이다.
"""
import re
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

SRC = "labs/day3/lab-c/hanbit_lunch_log.csv"
OUT = Path("workbench/day3/outputs/lunch_quality.md")

df = pd.read_csv(SRC, encoding="utf-8-sig", dtype=str, keep_default_na=False)
df.insert(0, "_row", df.index + 2)  # CSV 줄 번호(1줄 = 머리글)

WEEKDAYS = ["월", "화", "수", "목", "금"]
WEATHERS = ["맑음", "흐림", "비", "눈"]
MENU_VARIANTS = ["돈까스", "카레라이스", "제육", "치킨마요덮밥", "김치 찌개"]
EVENT_VARIANTS = ["외부손님", "전사교육"]


def parse_date(s):
    """여러 날짜 형식을 해석만 한다(원본은 그대로). 연도가 없으면 10–12월 2025, 1–9월 2026."""
    s = s.strip()
    m = re.fullmatch(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return pd.Timestamp(y, mo, d)
    m = re.fullmatch(r"(\d{1,2})월\s*(\d{1,2})일", s)
    if m:
        mo, d = map(int, m.groups())
        return pd.Timestamp(2025 if mo >= 10 else 2026, mo, d)
    return pd.NaT


def to_num(s):
    try:
        return float(s)
    except ValueError:
        return None


def md(frame):
    """tabulate 없이 Markdown 표로 바꾼다."""
    cols = [str(c) for c in frame.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in frame.itertuples(index=False):
        lines.append("| " + " | ".join("" if v is None else str(v) for v in row) + " |")
    return "\n".join(lines)


def show(v):
    """원본 글자 그대로 보여 주되 빈칸은 (빈칸)으로."""
    return f"`{v}`" if v != "" else "(빈칸)"


df["_date"] = df["날짜"].map(parse_date)
holiday = df["비고"] == "휴무"
working = ~holiday

# --- 엉망 종류별 마스크 -------------------------------------------------------
eat = df["식수"].map(to_num)
plan = df["출근예정"].map(to_num)
impossible = pd.Series(
    [
        (not h) and (e is not None) and (p is not None) and p > 0 and (e > p or e < 0.2 * p)
        for h, e, p in zip(holiday, eat, plan)
    ],
    index=df.index,
)
temp = df["최고기온"]
dup = df["_date"].duplicated(keep=False) & df["_date"].notna()

checks = [
    ("날짜 형식 섞임 (YYYY-MM-DD 아님)", ~df["날짜"].str.fullmatch(r"\d{4}-\d{2}-\d{2}"), "날짜"),
    ("요일 표기 섞임 (월–금 한 글자 아님)", ~df["요일"].isin(WEEKDAYS), "요일"),
    ("같은 날짜가 두 줄 (해당 줄 수)", dup, "날짜"),
    ("휴무 줄 (비고 = 휴무)", holiday, "비고"),
    ("식수 빈칸", df["식수"].str.strip() == "", "비고"),
    ("불가능해 보이는 식수 (식수 > 출근예정 또는 < 20%)", impossible, "식수"),
    ("날씨 표기 섞임 (맑음·흐림·비·눈 아님, 휴무 제외)", working & ~df["날씨"].isin(WEATHERS), "날씨"),
    ("최고기온 단위 붙음 (℃ · °C)", temp.str.contains("℃|°C", regex=True), "최고기온"),
    ("최고기온 빈칸 (휴무 제외)", working & (temp.str.strip() == ""), "최고기온"),
    ("메뉴 이름 섞임", df["메인메뉴"].isin(MENU_VARIANTS), "메인메뉴"),
    ("행사 이름 섞임", df["행사"].isin(EVENT_VARIANTS), "행사"),
    ("출근예정 빈칸", df["출근예정"].str.strip() == "", "날짜"),
]

rows = []
for name, mask, col in checks:
    hit = df[mask]
    if col in ("날짜",) and name.startswith(("같은", "출근")):
        ex = [f"{r['날짜']} (출근예정 {show(r['출근예정'])})" if name.startswith("출근") else f"{r['날짜']}"
              for _, r in hit.head(2).iterrows()]
    elif name.startswith("날짜 형식"):
        # 형식(숫자를 0으로 바꾼 모양)이 서로 다른 예시 2개
        shape = hit["날짜"].str.replace(r"\d", "0", regex=True)
        ex = [show(v) for v in hit.loc[~shape.duplicated(), "날짜"].head(2)]
    elif name.startswith(("식수 빈칸", "불가능")):
        ex = [f"{r['날짜']} 출근 {r['출근예정']} · 식수 {show(r['식수'])}" for _, r in hit.head(2).iterrows()]
    else:
        # 서로 다른 값으로 예시 2개
        ex = [show(v) for v in hit[col].drop_duplicates().head(2)]
    rows.append({"종류": name, "줄 수": len(hit), "예시 2개 (원본 그대로)": " · ".join(ex)})
issue_table = pd.DataFrame(rows)

# 같은 날짜 두 줄의 상세
dup_detail = df[dup].sort_values(["_date", "_row"])[["_row", "날짜", "출근예정", "식수", "비고"]]
dup_detail = dup_detail.rename(columns={"_row": "CSV 줄"})

# --- 비고 열 -----------------------------------------------------------------
memo = df.loc[df["비고"] != "", "비고"].value_counts().rename_axis("비고 (원본 그대로)").reset_index(name="줄 수")

# --- 사람이 정할 줄 -----------------------------------------------------------
decide_mask = impossible | (df["비고"] == "수기 집계")
# 재집계 표시가 없고 값도 서로 다른 쌍만(값이 똑같은 중복은 어느 줄을 남겨도 같다)
value_cols = [c for c in df.columns if not c.startswith("_") and c != "날짜"]
dup_dates_without_recount = [
    d for d, g in df[dup].groupby("_date")
    if not g["비고"].str.contains("재집계").any() and len(g[value_cols].drop_duplicates()) > 1
]
decide_mask |= df["_date"].isin(dup_dates_without_recount)
decide = df[decide_mask][["_row", "날짜", "출근예정", "식수", "비고"]].copy()
reasons = []
for i in decide.index:
    r = []
    if impossible[i]:
        e, p = eat[i], plan[i]
        r.append(f"식수가 출근예정의 {e / p:.1%}" + (" (출근보다 많음)" if e > p else " (20% 미만)"))
    if df.at[i, "비고"] == "수기 집계":
        r.append("비고 '수기 집계' — 빼거나 ×10 보정 중 결정 필요")
    if df.at[i, "_date"] in dup_dates_without_recount:
        r.append("같은 날짜 두 줄인데 '재집계' 표시 없음")
    reasons.append(" / ".join(r))
decide["왜 사람이 정하나"] = reasons
decide = decide.rename(columns={"_row": "CSV 줄"})

# --- 보고서 ------------------------------------------------------------------
dmin, dmax = df["_date"].min(), df["_date"].max()
unparsed = df["_date"].isna().sum()
parts = [
    "# 한빛식당 점심 기록 품질 진단",
    "",
    "> (가상) 한빛정밀(주) 본사 구내식당 '한빛식당'의 가상 기록. "
    f"원본 `{SRC}`는 읽기만 했고, 숫자는 모두 `scripts/lunch_quality.py`가 센 값이다.",
    "",
    "## 1. 기본",
    "",
    f"- 줄 수: **{len(df)}줄** (머리글 제외)",
    f"- 열 이름 ({len(df.columns) - 2}개): " + " · ".join(f"`{c}`" for c in df.columns if not c.startswith("_")),
    f"- 날짜 범위: **{dmin:%Y-%m-%d} ~ {dmax:%Y-%m-%d}** (여러 형식을 해석해 계산 · 해석 못 한 날짜 {unparsed}줄)",
    "",
    "## 2. 엉망인 곳 — 종류별",
    "",
    md(issue_table),
    "",
    "같은 날짜가 두 줄인 곳:",
    "",
    md(dup_detail),
    "",
    "## 3. 비고 열에 나오는 글",
    "",
    md(memo),
    "",
    "## 4. 사람이 정해야 할 줄",
    "",
    md(decide) if len(decide) else "없음",
    "",
]
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(parts), encoding="utf-8")
print("\n".join(parts))
print(f"\n저장: {OUT}")
