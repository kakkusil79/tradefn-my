"""3일차 실습 C: hanbit_lunch_log.csv 정제 (규칙 표: workbench/day3/outputs/lunch_rules.md)

실행: uv run python scripts/lunch_clean.py
결과: workbench/day3/outputs/lunch_clean.csv (UTF-8 BOM) · workbench/day3/outputs/lunch_clean_log.md
원본은 읽기만 한다. (가상) 한빛정밀(주) 본사 구내식당 '한빛식당'의 가상 기록이다.
적용 순서: R1 → R2 → R3 → R4 → R5 → R10 → R6 → R7 → R8 → R9
"""
import math
import re
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

SRC = "labs/day3/lab-c/hanbit_lunch_log.csv"
OUT_DIR = Path("workbench/day3/outputs")
OUT_CSV = OUT_DIR / "lunch_clean.csv"
OUT_LOG = OUT_DIR / "lunch_clean_log.md"

# R6 '수기 집계' 줄 — 수강생 결정: 뺀다
HANDWRITTEN_DECISION = "뺀다"

df = pd.read_csv(SRC, encoding="utf-8-sig", dtype=str, keep_default_na=False)
COLUMNS = list(df.columns)  # 원본과 같은 10개 열
n_start = len(df)
log = []  # (순서, 규칙, 할 일, 고친/뺀 줄 수)


def add_log(rule, what, n):
    log.append({"순서": len(log) + 1, "규칙": rule, "할 일": what, "줄 수": n})


def half_up(x):
    """반올림(0.5는 올림). 파이썬 round()는 짝수 쪽으로 가므로 쓰지 않는다."""
    return int(math.floor(x + 0.5))


# --- R1 날짜를 YYYY-MM-DD로 ---------------------------------------------------
def parse_date(s):
    s = s.strip()
    m = re.fullmatch(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return pd.Timestamp(y, mo, d)
    m = re.fullmatch(r"(\d{1,2})월\s*(\d{1,2})일", s)
    if m:
        mo, d = map(int, m.groups())
        return pd.Timestamp(2025 if mo >= 10 else 2026, mo, d)
    raise ValueError(f"해석 못 한 날짜: {s!r}")


new_date = df["날짜"].map(lambda s: parse_date(s).strftime("%Y-%m-%d"))
add_log("R1", "날짜를 YYYY-MM-DD로", int((new_date != df["날짜"]).sum()))
df["날짜"] = new_date

# --- R2 요일을 날짜에서 다시 계산 -------------------------------------------------
WD = ["월", "화", "수", "목", "금", "토", "일"]
WRITTEN = {"월요일": "월", "화요일": "화", "수요일": "수", "목요일": "목", "금요일": "금",
           "Mon": "월", "Tue": "화", "Wed": "수", "Thu": "목", "Fri": "금"}
actual = pd.to_datetime(df["날짜"]).dt.weekday.map(lambda i: WD[i])
written = df["요일"].str.strip().map(lambda s: WRITTEN.get(s, s))
add_log("R2", "요일을 날짜에서 다시 계산(적힌 요일이 실제와 달랐던 줄)", int((written != actual).sum()))
df["요일"] = actual

# --- R3 휴무 줄 빼기 ------------------------------------------------------------
mask = df["비고"].str.strip() == "휴무"
add_log("R3", "비고가 '휴무'인 줄 빼기", int(mask.sum()))
df = df[~mask].reset_index(drop=True)

# --- R4 같은 날짜 두 줄 → 재집계 줄, 없으면 나중 줄 --------------------------------
df["_order"] = range(len(df))  # 파일 안 순서(나중 줄 = 큰 값)
df["_recount"] = df["비고"].str.contains("재집계").astype(int)
keep = df.sort_values(["날짜", "_recount", "_order"]).groupby("날짜").tail(1).index
n_before = len(df)
df = df.loc[sorted(keep)].reset_index(drop=True)
add_log("R4", "같은 날짜 두 줄 → 재집계 줄(없으면 나중 줄)만 남기기", n_before - len(df))

# --- R5 식수 빈칸 빼기 ----------------------------------------------------------
mask = df["식수"].str.strip() == ""
add_log("R5", "식수 빈칸인 줄 빼기", int(mask.sum()))
df = df[~mask].reset_index(drop=True)

# --- R10 출근예정 빈칸 → 같은 요일 바로 앞 4개(출근예정 있는 줄)의 median ---------------
df = df.sort_values("날짜").reset_index(drop=True)
filled = 0
for i in df.index[df["출근예정"].str.strip() == ""]:
    prev = df[(df["요일"] == df.at[i, "요일"]) & (df["날짜"] < df.at[i, "날짜"])
              & (df["출근예정"].str.strip() != "")].tail(4)
    if len(prev) < 4:
        raise ValueError(f"{df.at[i, '날짜']}: 같은 요일 앞 기록이 4개보다 적음 — 확인 필요")
    value = half_up(prev["출근예정"].astype(float).median())
    print(f"R10 {df.at[i, '날짜']}({df.at[i, '요일']}) ← 앞 4개 {prev['출근예정'].tolist()} → {value}")
    df.at[i, "출근예정"] = str(value)
    filled += 1
add_log("R10", "출근예정 빈칸 채우기(같은 요일 앞 4개 median, 반올림)", filled)

# --- R6 불가능한 식수 · 수기 집계 ---------------------------------------------------
eat = df["식수"].astype(float)
plan = df["출근예정"].astype(float)
hand = df["비고"].str.strip() == "수기 집계"
impossible = (eat > plan) | (eat < 0.2 * plan)
if HANDWRITTEN_DECISION == "뺀다":
    drop = impossible | hand
    n_fixed = 0
elif HANDWRITTEN_DECISION == "×10 보정":
    df.loc[hand, "식수"] = (eat[hand] * 10).astype(int).astype(str)
    drop = impossible & ~hand
    n_fixed = int(hand.sum())
else:
    raise ValueError("'수기 집계' 줄 결정이 없음 — 수강생에게 묻는다")
for _, r in df[drop].iterrows():
    print(f"R6 뺌: {r['날짜']} 출근예정 {r['출근예정']} · 식수 {r['식수']} · 비고 {r['비고'] or '(없음)'}")
add_log("R6", f"불가능한 식수 줄 빼기('수기 집계' 줄: {HANDWRITTEN_DECISION})", int(drop.sum()) + n_fixed)
df = df[~drop].reset_index(drop=True)

# --- R7 날씨 넷으로 --------------------------------------------------------------
WEATHER = {"맑": "맑음", "sunny": "맑음", "구름많음": "흐림", "cloudy": "흐림",
           "rain": "비", "우천": "비", "소나기": "비", "흐리고 비": "비", "snow": "눈", "": "모름"}
new = df["날씨"].str.strip().map(lambda s: WEATHER.get(s, s))
bad = set(new) - {"맑음", "흐림", "비", "눈", "모름"}
if bad:
    raise ValueError(f"R7에 없는 날씨 표기: {bad} — 확인 필요")
add_log("R7", "날씨를 맑음 · 흐림 · 비 · 눈(빈칸은 모름)으로", int((new != df["날씨"]).sum()))
df["날씨"] = new

# --- R8 최고기온 숫자만 ------------------------------------------------------------
new = df["최고기온"].str.replace("℃", "", regex=False).str.replace("°C", "", regex=False).str.replace(r"\s", "", regex=True)
for v in new[new != ""]:
    float(v)  # 숫자로 안 바뀌면 여기서 멈춘다
add_log("R8", "최고기온에서 ℃ · °C · 공백 떼기", int((new != df["최고기온"]).sum()))
df["최고기온"] = new

# --- R9 메뉴 · 행사 이름 통일 --------------------------------------------------------
MENU = {"돈까스": "돈가스", "카레라이스": "카레", "제육": "제육볶음", "치킨마요덮밥": "치킨마요", "김치 찌개": "김치찌개"}
EVENT = {"외부손님": "외부 손님 방문", "전사교육": "전사 교육"}
n_menu = int(df["메인메뉴"].isin(MENU).sum())
n_event = int(df["행사"].isin(EVENT).sum())
df["메인메뉴"] = df["메인메뉴"].replace(MENU)
df["행사"] = df["행사"].replace(EVENT)
add_log("R9", f"메뉴 · 행사 이름 통일(메뉴 {n_menu} + 행사 {n_event})", n_menu + n_event)

# --- 마지막 정리 · 저장 --------------------------------------------------------------
df["월급날"] = df["월급날"].str.strip().map({"Y": 1, "": 0})
df["출근예정"] = df["출근예정"].astype(int)
df["식수"] = df["식수"].astype(int)
df = df.sort_values("날짜")[COLUMNS].reset_index(drop=True)
assert df["날짜"].is_unique

OUT_DIR.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

log_df = pd.DataFrame(log)
lines = [
    "# 한빛식당 점심 기록 정제 기록",
    "",
    "> (가상) 한빛정밀(주) 본사 구내식당 '한빛식당'의 가상 기록. 규칙 표는 `lunch_rules.md`, 숫자는 `scripts/lunch_clean.py`가 센 값이다.",
    "> 세는 법: 그 규칙을 적용할 때 남아 있는 줄에서 센다. R2는 적힌 요일이 실제 요일과 달랐던 줄만, R9는 메뉴와 행사를 따로 세어 더한다.",
    "",
    f"- 처음 줄 수: **{n_start}줄** → 남은 줄 수: **{len(df)}줄**",
    f"- '수기 집계' 줄: **{HANDWRITTEN_DECISION}**",
    f"- 날짜 범위: {df['날짜'].min()} ~ {df['날짜'].max()}",
    "",
    "| " + " | ".join(log_df.columns) + " |",
    "|" + "---|" * len(log_df.columns),
]
lines += ["| " + " | ".join(str(v) for v in r) + " |" for r in log_df.itertuples(index=False)]
OUT_LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")

print("\n".join(lines))
print(f"\n저장: {OUT_CSV} · {OUT_LOG}")
