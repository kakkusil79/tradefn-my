"""3일차 실습 C: 한빛식당 밥 예보 페이지 (workbench/day3/outputs/hanbit_lunch.html)

실행: uv run python scripts/lunch_page.py
입력: workbench/day3/outputs/lunch_clean.csv · labs/day3/lab-c/nutritionist_memo.md (읽기만)
페이지는 손으로 고치지 않는다 — 이 스크립트가 계산해서 쓴다(같은 입력이면 같은 페이지).
구역: 머리 → 예보 성적표 → 영양사님 감 검증
(가상) 한빛정밀(주) 본사 구내식당 '한빛식당'의 가상 기록이다.
"""
import html
import json
import math
import re
import sys
from pathlib import Path

import sklearn

# 이 PC의 Windows Visual C++ 런타임(msvcp140 · vcomp140)이 2015년판(14.00)이라 LightGBM이
# 'access violation reading 0x0'으로 멈춘다. scikit-learn에 든 새 런타임을 먼저 불러 둔다.
# Microsoft Visual C++ 재배포 패키지(x64)를 새로 설치하면 이 부분은 없어도 된다.
if sys.platform == "win32":
    import ctypes
    _libs = Path(sklearn.__file__).parent / ".libs"
    for _dll in ("msvcp140.dll", "vcomp140.dll"):
        if (_libs / _dll).exists():
            ctypes.WinDLL(str(_libs / _dll))

import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.linear_model import LinearRegression

sys.stdout.reconfigure(encoding="utf-8")

CLEAN = "workbench/day3/outputs/lunch_clean.csv"
MEMO = "labs/day3/lab-c/nutritionist_memo.md"
OUT = Path("workbench/day3/outputs/hanbit_lunch.html")

THRESHOLD = 2.0  # 100명당 2명 이상 차이 = '차이 있음'(사람이 정한 선)

ACCENT = "#1f5fbf"
WARN = "#c2410c"
GRAY = "#8a919c"
BADGE_COLOR = {"맞음": ACCENT, "반만": GRAY, "틀림": WARN}

df = pd.read_csv(CLEAN, encoding="utf-8-sig")
df["per100"] = df["식수"] / df["출근예정"] * 100
normal = df[df["행사"].isna() & (df["월급날"] == 0)]  # 행사 없고 월급날 아닌 날


def esc(s):
    return html.escape(str(s))


# --- 감 노트에서 믿음 글 읽기 ----------------------------------------------------------
def read_beliefs():
    text = Path(MEMO).read_text(encoding="utf-8")
    part = text.split("## 제가 믿는 다섯 가지", 1)[1].split("##", 1)[0]
    found = {}
    for line in part.splitlines():
        m = re.match(r"^(\d)\.\s+\*\*(.+?)\*\*\s*(.*)$", line.strip())
        if m:
            found[int(m.group(1))] = {"head": m.group(2), "tail": m.group(3)}
    assert sorted(found) == [1, 2, 3, 4, 5], "감 노트의 믿음 다섯 가지를 못 찾음 — 확인 필요"
    return found


BELIEFS = read_beliefs()


# --- 계산 · 판정 ---------------------------------------------------------------------
def group(frame, label):
    return {"label": label, "value": round(float(frame["per100"].mean()), 1),
            "_raw": float(frame["per100"].mean()), "days": int(len(frame))}


def judge_pair(a, b, expect):
    """expect = +1: a가 b보다 많다는 믿음 / -1: a가 b보다 적다는 믿음."""
    diff = a["_raw"] - b["_raw"]
    if abs(diff) < THRESHOLD:
        return "반만", diff
    return ("맞음" if diff * expect > 0 else "틀림"), diff


def pair_card(no, a, b, expect, note=""):
    verdict, diff = judge_pair(a, b, expect)
    return {"no": no, **BELIEFS[no], "kind": "pair", "groups": [a, b],
            "diff": round(diff, 1), "verdict": verdict, "note": note}


cards = []

# 믿음 1 비 오는 날 vs 맑은 날 (비가 많다는 믿음)
cards.append(pair_card(1, group(normal[normal["날씨"] == "비"], "비 오는 날"),
                       group(normal[normal["날씨"] == "맑음"], "맑은 날"), +1))

# 믿음 2 금요일 vs 월–목 (금요일이 적다는 믿음)
cards.append(pair_card(2, group(normal[normal["요일"] == "금"], "금요일"),
                       group(normal[normal["요일"].isin(["월", "화", "수", "목"])], "월–목"), -1))

# 믿음 3 메뉴별(높은 순) — 돈가스가 1등이고 2등보다 2명 이상 많으면 맞음
menu = (normal.groupby("메인메뉴")["per100"].agg(["mean", "size"])
        .sort_values("mean", ascending=False))
ranking = [{"label": m, "value": round(float(r["mean"]), 1), "_raw": float(r["mean"]), "days": int(r["size"])}
           for m, r in menu.iterrows()]
top, second = ranking[0], ranking[1]
donkatsu = next(r for r in ranking if r["label"] == "돈가스")
dk_rank = ranking.index(donkatsu) + 1
if top["label"] == "돈가스" and top["_raw"] - second["_raw"] >= THRESHOLD:
    v3 = "맞음"
elif top["_raw"] - donkatsu["_raw"] < THRESHOLD:
    v3 = "반만"
else:
    v3 = "틀림"
other_best = second if top["label"] == "돈가스" else top
cards.append({"no": 3, **BELIEFS[3], "kind": "menu", "groups": [donkatsu, other_best],
              "ranking": ranking, "rank": dk_rank, "verdict": v3,
              "diff": round(donkatsu["_raw"] - other_best["_raw"], 1),
              "note": f"돈가스는 {len(ranking)}개 메뉴 중 {dk_rank}등"})

# 믿음 4 31도 이상 vs 25도 이상 31도 미만 (더우면 적다는 믿음) — 기온 빈칸은 뺀다
hot = normal[normal["최고기온"] >= 31]
warm = normal[(normal["최고기온"] >= 25) & (normal["최고기온"] < 31)]
cards.append(pair_card(4, group(hot, "31도 이상"), group(warm, "25도 이상 31도 미만"), -1,
                       note=f"31도 이상인 날 {len(hot)}일"))

# 믿음 5 월요일 vs 화–목 (월요일이 적다는 믿음)
cards.append(pair_card(5, group(normal[normal["요일"] == "월"], "월요일"),
                       group(normal[normal["요일"].isin(["화", "수", "목"])], "화–목"), -1))

# 메모에 없던 규칙: 월급날(월급날인 날 모두) vs 보통 날
pay = group(df[df["월급날"] == 1], "월급날")
base = group(normal, "보통 날")
pay_diff = pay["_raw"] - base["_raw"]
payday = {"kind": "extra", "head": "월급날엔 더 올까, 덜 올까?",
          "tail": "영양사님 메모에는 없던 규칙입니다. 9/23 사건 메모에 '월급날이기도 했고요'라는 말만 있었어요.",
          "groups": [pay, base], "diff": round(pay_diff, 1),
          "verdict": ("차이 있음" if abs(pay_diff) >= THRESHOLD else "차이 작음"),
          "note": "월급날은 행사가 있는 날도 모두 넣었어요"}

# --- 예보관 시험 ------------------------------------------------------------------------
TEST_START = "2026-09-14"  # 이 날부터 시험 기간(배울 때 쓰지 않는다)
MARGIN = 10  # AI 준비 = 예보 + 10
COST = 4500  # 1인분 원가(가정)
TEXT_COLS = ["요일", "날씨", "메인메뉴", "행사"]
NUM_COLS = ["최고기온", "월급날", "출근예정"]
MENU_FACTOR = {"돈가스": 1.1, "카레": 1.1, "샐러드": 0.9}  # 나머지 1.0


def half_up(x):
    """반올림(0.5는 올림)."""
    return int(math.floor(x + 0.5))


train = df[df["날짜"] < TEST_START].copy()
test = df[df["날짜"] >= TEST_START].copy()
TEMP_FILL = float(train["최고기온"].median())  # 최고기온 빈칸 = 배우는 기간의 가운데 값


def features(frame, columns=None):
    x = frame[TEXT_COLS + NUM_COLS].copy()
    x["최고기온"] = x["최고기온"].fillna(TEMP_FILL)
    x["행사"] = x["행사"].fillna("없음")
    x = pd.get_dummies(x, columns=TEXT_COLS, dtype=int)  # drop_first 없이
    if columns is not None:
        x = x.reindex(columns=columns, fill_value=0)  # 배울 때와 같은 열, 없는 열은 0
    return x


X_train = features(train).astype(float)
FEATURE_COLS = list(X_train.columns)
X_test = features(test, FEATURE_COLS).astype(float)
# LightGBM에는 pandas 열 대신 숫자 배열로 넘긴다(pandas 열을 그대로 넘기면 멈춘다)
y_train = train["식수"].to_numpy(dtype=float)
y_test = test["식수"].astype(float)

forecasters = {
    "선형 회귀": LinearRegression(),
    "LightGBM": LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=15,
                              min_child_samples=5, random_state=42, verbose=-1),
}
pred, mae = {}, {}
for name, model in forecasters.items():
    model.fit(X_train, y_train)
    pred[name] = pd.Series(model.predict(X_test), index=test.index)
    mae[name] = float((pred[name] - y_test).abs().mean())
OUR = min(mae, key=mae.get)  # 시험 성적이 더 작은 쪽 = 우리 예보관
OUR_MODEL = forecasters[OUR]


def formula(day, menu_name, history):
    """영양사님 공식: 그날 전 같은 요일 실제 식수 4개 평균 × 메뉴 배수."""
    prev = history[(history["날짜"] < day["날짜"]) & (history["요일"] == day["요일"])].tail(4)
    assert len(prev) == 4, f"{day['날짜']}: 같은 요일 앞 기록이 4개보다 적음 — 확인 필요"
    return float(prev["식수"].mean()) * MENU_FACTOR.get(menu_name, 1.0)


test["ai"] = pred[OUR]
test["formula"] = [formula(r, r["메인메뉴"], df) for _, r in test.iterrows()]
test["ai_prep"] = test["ai"].map(half_up) + MARGIN
test["formula_prep"] = test["formula"].map(half_up)


def outcome(prep_col, fc_col):
    left = (test[prep_col] - test["식수"]).clip(lower=0)
    short = (test["식수"] - test[prep_col]).clip(lower=0)
    return {"mae": round(float((test[fc_col] - test["식수"]).abs().mean()), 1),
            "left": int(left.sum()), "left_won": int(left.sum()) * COST,
            "short": int(short.sum()), "short_days": int((short > 0).sum())}


result = {"ai": outcome("ai_prep", "ai"), "formula": outcome("formula_prep", "formula")}

EVENTS = {"2026-09-23": "추석 연휴 전날 · 돈가스", "2026-09-30": "비 오는 수요일 · 카레"}
event_rows = []
for d, title in EVENTS.items():
    r = test[test["날짜"] == d].iloc[0]
    event_rows.append({"date": d, "title": title, "actual": int(r["식수"]),
                       "ai": half_up(r["ai"]), "ai_prep": int(r["ai_prep"]),
                       "formula": int(r["formula_prep"])})

scorecard = {
    "our": OUR,
    "mae": {k: round(v, 1) for k, v in mae.items()},
    "labels": [f"{int(d[5:7])}/{int(d[8:])}" for d in test["날짜"]],
    "dates": list(test["날짜"]),
    "actual": [int(v) for v in test["식수"]],
    "ai": [half_up(v) for v in test["ai"]],
    "formula": [int(v) for v in test["formula_prep"]],
    "events": event_rows,
    "result": result,
}

# --- 다음 주 예보 ------------------------------------------------------------------------
PLAN = "labs/day3/lab-c/next_week_plan.csv"
plan = pd.read_csv(PLAN, encoding="utf-8-sig")
plan = plan.rename(columns={"날씨예보": "날씨", "최고기온예보": "최고기온"})
plan["월급날"] = plan["월급날"].map(lambda v: 1 if str(v).strip() == "Y" else 0)
X_plan = features(plan, FEATURE_COLS).astype(float)  # 배울 때와 같은 열, 행사 빈칸 → '없음'
plan["ai"] = OUR_MODEL.predict(X_plan)
plan["forecast"] = plan["ai"].map(half_up)
plan["prep"] = plan["forecast"] + MARGIN
plan["formula"] = [half_up(formula(r, r["메인메뉴"], df)) for _, r in plan.iterrows()]
max_i, min_i = plan["forecast"].idxmax(), plan["forecast"].idxmin()

verdict_of = {c["no"]: c["verdict"] for c in cards}


def comment(r):
    """영양사님께 드리는 한 줄 — 그날 조건과 영양사님 공식과의 차이(숫자는 계산값만)."""
    notes = []
    if r["월급날"] == 1 and pay_diff <= -THRESHOLD:
        notes.append(f"월급날이라 지난 기록에선 100명당 {abs(pay_diff):.1f}명 덜 오셨어요")
    if isinstance(r["행사"], str) and r["행사"].strip():
        notes.append(f"{r['행사']}이 있는 날이에요")
    if r["날씨"] == "비" and verdict_of[1] == "맞음":
        notes.append("비 오는 날은 지난 기록에서도 더 오셨어요")
    if r["요일"] == "금" and verdict_of[2] == "맞음":
        notes.append("금요일은 지난 기록에서도 적게 오셨어요")
    if r["요일"] == "월" and verdict_of[5] == "틀림":
        notes.append("월요일이라고 적게 오시진 않았어요")
    if r["메인메뉴"] in MENU_FACTOR:
        notes.append(f"{r['메인메뉴']} 날이라 공식은 평균의 {MENU_FACTOR[r['메인메뉴']]:.1f}배예요")
    gap = int(r["prep"] - r["formula"])
    if gap < 0:
        tail = f"준비는 공식보다 {abs(gap)}인분 적게 해도 될 것 같아요."
    elif gap > 0:
        tail = f"준비는 공식보다 {gap}인분 넉넉히 하시면 좋겠어요."
    else:
        tail = "준비는 공식과 같아요."
    lead = notes[0] + ". " if notes else ""
    return f"영양사님, {lead}{tail}"


plan["comment"] = [comment(r) for _, r in plan.iterrows()]

nextweek = [{
    "date": r["날짜"], "label": f"{int(r['날짜'][5:7])}/{int(r['날짜'][8:])}", "dow": r["요일"],
    "forecast": int(r["forecast"]), "prep": int(r["prep"]), "formula": int(r["formula"]),
    "weather": r["날씨"], "menu": r["메인메뉴"],
    "event": r["행사"] if isinstance(r["행사"], str) and r["행사"].strip() else "",
    "payday": int(r["월급날"]), "comment": r["comment"],
    "mark": "이번 주 가장 많은 날" if i == max_i else ("이번 주 가장 적은 날" if i == min_i else ""),
} for i, r in plan.iterrows()]

# --- 화면에 넘길 데이터(JSON) -----------------------------------------------------------
def public(obj):
    """'_'로 시작하는 계산용 값은 빼고 넘긴다."""
    if isinstance(obj, dict):
        return {k: public(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [public(v) for v in obj]
    return obj


period = f"{df['날짜'].min()} ~ {df['날짜'].max()}"
DATA = {"beliefs": public(cards), "payday": public(payday), "scorecard": scorecard, "nextweek": nextweek,
        "colors": {"accent": ACCENT, "warn": WARN, "gray": GRAY}}


# --- 구역 만들기 ------------------------------------------------------------------------
def fmt_diff(d):
    return f"{d:+.1f}명"


def header_html():
    return f"""
<header class="head">
  <h1>한빛식당 밥 예보</h1>
  <p class="lede">(가상) 한빛정밀(주) 본사 구내식당 · 기록 기간 {esc(period)} · 만든 사람 총무팀 최 대리(가상)</p>
</header>"""


def numbers_html(groups):
    cells = "".join(
        f'<div class="num"><span class="num-label">{esc(g["label"])}</span>'
        f'<span class="num-value">{g["value"]:.1f}<small>명</small></span>'
        f'<span class="num-days">{g["days"]}일</span></div>'
        for g in groups)
    return f'<div class="nums">{cells}</div>'


def belief_card(c, idx):
    color = BADGE_COLOR[c["verdict"]]
    note = f'<p class="note">{esc(c["note"])}</p>' if c.get("note") else ""
    if c["kind"] == "menu":
        diff_line = f'돈가스 − {esc(c["groups"][1]["label"])} = {fmt_diff(c["diff"])}'
        chart_h = 34 + 22 * len(c["ranking"])
    else:
        diff_line = f'{esc(c["groups"][0]["label"])} − {esc(c["groups"][1]["label"])} = {fmt_diff(c["diff"])}'
        chart_h = 96
    return f"""
  <article class="card">
    <div class="card-top">
      <span class="no">믿음 {c["no"]}</span>
      <span class="badge" style="background:{color}">{esc(c["verdict"])}</span>
    </div>
    <h3>{esc(c["head"])}</h3>
    <p class="quote">{esc(c["tail"])}</p>
    {numbers_html(c["groups"])}
    <p class="diff">출근 100명당 차이: {diff_line}</p>
    {note}
    <div class="chart" style="height:{chart_h}px"><canvas id="b{idx}" aria-label="믿음 {c["no"]} 막대 그래프"></canvas></div>
  </article>"""


def payday_card(c):
    note = f'<p class="note">{esc(c["note"])}</p>'
    return f"""
  <article class="card card-extra">
    <div class="card-top">
      <span class="no">메모에 없던 규칙</span>
      <span class="badge badge-outline">{esc(c["verdict"])}</span>
    </div>
    <h3>{esc(c["head"])}</h3>
    <p class="quote">{esc(c["tail"])}</p>
    {numbers_html(c["groups"])}
    <p class="diff">출근 100명당 차이: 월급날 − 보통 날 = {fmt_diff(c["diff"])}</p>
    {note}
    <div class="chart" style="height:96px"><canvas id="bp" aria-label="월급날 막대 그래프"></canvas></div>
  </article>"""


def won(n):
    return f"{n:,}원"


def nextweek_section():
    def day_card(d):
        chips = [d["weather"], d["menu"]] + ([d["event"]] if d["event"] else []) + (["월급날"] if d["payday"] else [])
        chip_html = "".join(f'<span class="chip">{esc(c)}</span>' for c in chips)
        mark = f'<span class="mark">{esc(d["mark"])}</span>' if d["mark"] else ""
        cls = " day-max" if "많은" in d["mark"] else (" day-min" if "적은" in d["mark"] else "")
        return f"""
    <article class="day{cls}">
      <div class="day-top"><span class="day-date">{esc(d["label"])} ({esc(d["dow"])})</span>{mark}</div>
      <div class="day-big">{d["forecast"]}<small>명</small></div>
      <div class="day-prep">준비 {d["prep"]}인분</div>
      <div class="day-formula">영양사님 공식이면 {d["formula"]}인분</div>
      <div class="chips">{chip_html}</div>
      <p class="day-comment">{esc(d["comment"])}</p>
    </article>"""

    days = "".join(day_card(d) for d in nextweek)
    first, last = nextweek[0], nextweek[-1]
    return f"""
<section class="section" id="nextweek">
  <h2>다음 주 예보 <span class="h2-sub">{esc(first["label"])} ~ {esc(last["label"])}</span></h2>
  <p class="section-lede">시험에서 이긴 우리 예보관({esc(OUR)})에게 다음 주 계획(메뉴 · 날씨예보 · 행사 · 월급날 · 출근예정)을 물었어요.
    준비 = 예보 + {MARGIN}인분이에요.</p>
  <div class="week">{days}
  </div>
</section>"""


def scorecard_section():
    s = scorecard
    other = next(k for k in s["mae"] if k != s["our"])
    judges = "".join(
        f'<div class="judge{" judge-pick" if k == s["our"] else ""}">'
        f'<span class="judge-name">{esc(k)}</span>'
        f'<span class="judge-value">{v:.1f}<small>인분</small></span>'
        f'<span class="judge-sub">{"우리 예보관으로 고름" if k == s["our"] else "하루 평균 차이"}</span></div>'
        for k, v in s["mae"].items())
    events = "".join(
        f'<li><b>{int(e["date"][5:7])}/{int(e["date"][8:])} {esc(e["title"])}</b> — 실제 {e["actual"]}명 · '
        f'AI 예보 {e["ai"]}명(준비 {e["ai_prep"]}인분) · 영양사님 공식 {e["formula"]}인분</li>'
        for e in s["events"])
    a, f = s["result"]["ai"], s["result"]["formula"]

    def compare(title, ai_main, ai_sub, f_main, f_sub):
        return f"""
    <article class="card">
      <h3>{title}</h3>
      <div class="nums">
        <div class="num"><span class="num-label">AI({esc(s["our"])} + {MARGIN}인분)</span>
          <span class="num-value">{ai_main}</span><span class="num-days">{ai_sub}</span></div>
        <div class="num"><span class="num-label">영양사님 공식</span>
          <span class="num-value">{f_main}</span><span class="num-days">{f_sub}</span></div>
      </div>
    </article>"""

    cmp_cards = (
        compare("하루 평균 몇 인분 차이", f'{a["mae"]:.1f}<small>인분</small>', "예보와 실제",
                f'{f["mae"]:.1f}<small>인분</small>', "공식과 실제")
        + compare("남은 밥", f'{a["left"]:,}<small>인분</small>', won(a["left_won"]),
                  f'{f["left"]:,}<small>인분</small>', won(f["left_won"]))
        + compare("모자란 밥 = 컵라면을 드신 분", f'{a["short"]:,}<small>인분</small>', f'모자란 날 {a["short_days"]}일',
                  f'{f["short"]:,}<small>인분</small>', f'모자란 날 {f["short_days"]}일'))
    return f"""
<section class="section" id="scorecard">
  <h2>예보 성적표</h2>
  <p class="section-lede">{esc(s["dates"][0])}보다 앞선 기록으로 AI 예보관 두 명을 가르치고,
    그 뒤 {len(s["dates"])}일({esc(s["dates"][0])} ~ {esc(s["dates"][-1])})은 가르칠 때 쓰지 않고 시험만 봤어요.
    설정은 모두 같은 결과를 보려고 고정했어요.</p>
  <div class="judges">{judges}</div>
  <p class="tagline">복잡한 쪽이 늘 이기지는 않는다 — 시험으로 고른다. 이번 시험에서는 {esc(s["our"])}가
    {esc(other)}보다 하루 평균 {abs(s["mae"][other] - s["mae"][s["our"]]):.1f}인분 덜 틀렸어요.</p>
  <div class="card card-wide">
    <h3>시험 {len(s["dates"])}일 — 실제 · 우리 예보관 · 영양사님 공식</h3>
    <div class="chart" style="height:300px"><canvas id="testline" aria-label="시험 기간 선 그래프"></canvas></div>
    <ul class="events">{events}</ul>
  </div>
  <p class="section-lede">준비량으로 바꿔 보면 — AI 준비 = 예보 + {MARGIN}인분, 영양사님 준비 = 공식.
    1인분 원가는 {won(COST)}으로 가정했어요.</p>
  <div class="grid">{cmp_cards}
  </div>
</section>"""


def beliefs_section():
    body = "".join(belief_card(c, i) for i, c in enumerate(cards)) + payday_card(payday)
    count = {v: sum(c["verdict"] == v for c in cards) for v in ("맞음", "반만", "틀림")}
    return f"""
<section class="section" id="beliefs">
  <h2>영양사님 감 검증</h2>
  <p class="section-lede">영양사님의 믿음 다섯 가지를 지난 기록으로 견주어 봤어요.
    출근 인원이 다른 날도 견줄 수 있게 <b>출근 100명당 식수</b>(식수 ÷ 출근예정 × 100)로 비교했고,
    행사가 없고 월급날이 아닌 날만 썼어요. 100명당 2명 이상 차이 나면 '차이 있음'으로 봤어요.</p>
  <p class="tally">맞음 {count["맞음"]} · 반만 {count["반만"]} · 틀림 {count["틀림"]}</p>
  <div class="grid">{body}
  </div>
</section>"""


CSS = """
:root{--bg:#f4f5f7;--card:#ffffff;--ink:#1d2330;--sub:#5b6472;--line:#e3e6eb;--accent:%(accent)s;--warn:%(warn)s;--gray:%(gray)s}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font-family:'Noto Sans KR',sans-serif;font-size:16px;line-height:1.6;word-break:keep-all;overflow-wrap:break-word}
.wrap{max-width:1040px;margin:0 auto;padding:24px 16px 48px}
.head{padding:8px 0 20px;border-bottom:1px solid var(--line);margin-bottom:24px}
h1{font-size:30px;line-height:1.3;margin:0 0 6px;font-weight:700}
.lede{margin:0;color:var(--sub);font-size:15px}
h2{font-size:22px;margin:0 0 8px}
.section-lede{margin:0 0 6px;color:var(--sub);font-size:15px}
.tally{margin:0 0 16px;font-weight:700;font-size:15px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%%,300px),1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;display:flex;flex-direction:column;min-width:0}
.card-extra{border-style:dashed}
.card-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.no{font-size:14px;color:var(--sub);font-weight:700}
.badge{color:#fff;font-size:14px;font-weight:700;padding:2px 12px;border-radius:999px}
.badge-outline{background:transparent;color:var(--ink);border:1px solid var(--gray)}
h3{font-size:18px;margin:0 0 4px;line-height:1.4}
.quote{margin:0 0 12px;color:var(--sub);font-size:14px}
.nums{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px}
.num{background:var(--bg);border-radius:8px;padding:8px 10px;display:flex;flex-direction:column;min-width:0}
.num-label{font-size:14px;color:var(--sub)}
.num-value{font-size:24px;font-weight:700;line-height:1.3;font-variant-numeric:tabular-nums}
.num-value small{font-size:14px;font-weight:400;margin-left:2px}
.num-days{font-size:14px;color:var(--sub)}
.diff{margin:0;font-size:14px}
.note{margin:2px 0 0;font-size:14px;color:var(--sub)}
.chart{position:relative;margin-top:10px;width:100%%}
.section{margin-bottom:40px}
.judges{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0}
.judge{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;min-width:0}
.judge-pick{border:2px solid var(--accent)}
.judge-name{font-size:15px;font-weight:700}
.judge-value{font-size:28px;font-weight:700;line-height:1.3;font-variant-numeric:tabular-nums}
.judge-value small{font-size:14px;font-weight:400;margin-left:2px}
.judge-sub{font-size:14px;color:var(--sub)}
.judge-pick .judge-sub{color:var(--accent);font-weight:700}
.tagline{margin:0 0 16px;font-size:15px;font-weight:700}
.card-wide{margin-bottom:16px}
.events{margin:10px 0 0;padding-left:18px;font-size:14px}
.events li{margin-bottom:4px}
.h2-sub{font-size:15px;font-weight:400;color:var(--sub);margin-left:6px}
.week{display:grid;grid-template-columns:1fr;gap:12px}
@media (min-width:900px){.week{grid-template-columns:repeat(5,minmax(0,1fr))}}
.day{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;display:flex;flex-direction:column;min-width:0}
.day-max{border:2px solid var(--accent)}
.day-min{border:2px solid var(--warn)}
.day-top{display:flex;justify-content:space-between;align-items:center;gap:6px;flex-wrap:wrap}
.day-date{font-size:16px;font-weight:700}
.mark{font-size:14px;font-weight:700;color:#fff;background:var(--accent);border-radius:999px;padding:1px 10px}
.day-min .mark{background:var(--warn)}
.day-big{font-size:40px;font-weight:700;line-height:1.2;margin-top:6px;font-variant-numeric:tabular-nums}
.day-big small{font-size:16px;font-weight:400;margin-left:2px}
.day-prep{font-size:17px;font-weight:700;color:var(--accent)}
.day-formula{font-size:14px;color:var(--sub)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 8px}
.chip{font-size:14px;border:1px solid var(--line);background:var(--bg);border-radius:999px;padding:1px 10px}
.day-comment{margin:auto 0 0;font-size:14px;color:var(--ink)}
""" % {"accent": ACCENT, "warn": WARN, "gray": GRAY}

JS = r"""
const D = JSON.parse(document.getElementById('page-data').textContent);
const C = D.colors;
Chart.defaults.font.family = "'Noto Sans KR', sans-serif";
Chart.defaults.font.size = 14;
function bars(id, labels, values, colors) {
  new Chart(document.getElementById(id), {
    type: 'bar',
    data: {labels: labels, datasets: [{data: values, backgroundColor: colors, borderRadius: 4, barThickness: 16}]},
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false, animation: false,
      plugins: {legend: {display: false},
        tooltip: {callbacks: {label: (c) => '100명당 ' + c.parsed.x.toFixed(1) + '명'}}},
      scales: {x: {beginAtZero: false, grid: {color: '#eceef1'}, ticks: {callback: (v) => v + '명'}},
               y: {grid: {display: false}}}
    }
  });
}
D.beliefs.forEach((b, i) => {
  if (b.kind === 'menu') {
    bars('b' + i, b.ranking.map(r => r.label), b.ranking.map(r => r.value),
         b.ranking.map(r => r.label === '돈가스' ? C.accent : '#c9ced6'));
  } else {
    bars('b' + i, b.groups.map(g => g.label), b.groups.map(g => g.value), [C.accent, '#c9ced6']);
  }
});
bars('bp', D.payday.groups.map(g => g.label), D.payday.groups.map(g => g.value), [C.accent, '#c9ced6']);

// 예보 성적표 — 시험 기간 선 그래프, 9/23 · 9/30에 세로 표시
const S = D.scorecard;
const markIdx = S.events.map(e => S.dates.indexOf(e.date));
const markers = {
  id: 'markers',
  afterDatasetsDraw(chart) {
    const {ctx, chartArea, scales} = chart;
    ctx.save();
    markIdx.forEach(i => {
      const x = scales.x.getPixelForValue(i);
      ctx.strokeStyle = C.warn; ctx.setLineDash([4, 4]); ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
      ctx.setLineDash([]); ctx.fillStyle = C.warn; ctx.font = "700 14px 'Noto Sans KR', sans-serif";
      ctx.textAlign = x > chartArea.right - 40 ? 'right' : 'center';
      ctx.fillText(S.labels[i], x, chartArea.top + 14);
    });
    ctx.restore();
  }
};
const pointR = (base) => S.dates.map((d, i) => markIdx.includes(i) ? base + 2 : base);
new Chart(document.getElementById('testline'), {
  type: 'line',
  data: {labels: S.labels, datasets: [
    {label: '실제', data: S.actual, borderColor: '#1d2330', backgroundColor: '#1d2330', borderWidth: 2.5, pointRadius: pointR(2.5), tension: 0},
    {label: '우리 예보관(' + S.our + ')', data: S.ai, borderColor: C.accent, backgroundColor: C.accent, borderWidth: 2, pointRadius: pointR(2), tension: 0},
    {label: '영양사님 공식', data: S.formula, borderColor: C.gray, backgroundColor: C.gray, borderWidth: 2, borderDash: [6, 4], pointRadius: pointR(2), tension: 0}
  ]},
  options: {
    responsive: true, maintainAspectRatio: false, animation: false,
    interaction: {mode: 'index', intersect: false},
    plugins: {legend: {position: 'bottom', labels: {boxWidth: 14}},
      tooltip: {callbacks: {label: (c) => c.dataset.label + ' ' + c.parsed.y + '명'}}},
    scales: {y: {grid: {color: '#eceef1'}, ticks: {callback: (v) => v + '명'}},
             x: {grid: {display: false}, ticks: {maxRotation: 0, autoSkip: true}}}
  },
  plugins: [markers]
});
"""


def page():
    data_json = json.dumps(DATA, ensure_ascii=False, indent=1).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>한빛식당 밥 예보</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
{header_html()}
{nextweek_section()}
{scorecard_section()}
{beliefs_section()}
</div>
<script id="page-data" type="application/json">{data_json}</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script>{JS}</script>
</body>
</html>
"""


OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(page(), encoding="utf-8")

# --- 화면 출력(확인용) --------------------------------------------------------------------
print(f"기록 기간 {period} · 깨끗한 표 {len(df)}줄 · 보통 날(행사 없고 월급날 아님) {len(normal)}일\n")
print("| 믿음 | 견준 두 숫자 (출근 100명당) | 차이 | 배지 |")
print("|---|---|---|---|")
for c in cards:
    a, b = c["groups"]
    print(f"| {c['no']} {c['head']} | {a['label']} {a['value']:.1f}명({a['days']}일) vs "
          f"{b['label']} {b['value']:.1f}명({b['days']}일) | {c['diff']:+.1f} | {c['verdict']} |")
print(f"| 메모에 없음 · 월급날 | 월급날 {pay['value']:.1f}명({pay['days']}일) vs 보통 날 {base['value']:.1f}명({base['days']}일) "
      f"| {payday['diff']:+.1f} | {payday['verdict']} |")
print("\n메뉴 순위: " + " > ".join(f"{r['label']} {r['value']:.1f}" for r in ranking))
print(f"31도 이상인 날: {len(hot)}일")

print(f"\n[예보 성적표] 배우는 기간 {len(train)}일 · 시험 기간 {len(test)}일 · 최고기온 빈칸 채움 {TEMP_FILL}")
for k, v in mae.items():
    print(f"  {k}: 하루 평균 {v:.2f}인분 차이" + ("  ← 우리 예보관" if k == OUR else ""))
for e in event_rows:
    print(f"  {e['date']} {e['title']}: 실제 {e['actual']} · AI 예보 {e['ai']}(준비 {e['ai_prep']}) · 공식 {e['formula']}")
for k, label in (("ai", "AI"), ("formula", "공식")):
    r = result[k]
    print(f"  {label}: 평균 차이 {r['mae']} · 남은 밥 {r['left']}인분({r['left_won']:,}원) · "
          f"모자란 밥 {r['short']}인분 · 모자란 날 {r['short_days']}일")
print(f"\n[다음 주 예보] 우리 예보관 {OUR}")
for d in nextweek:
    print(f"  {d['date']}({d['dow']}) {d['menu']}·{d['weather']}{'·' + d['event'] if d['event'] else ''}"
          f"{'·월급날' if d['payday'] else ''}: 예보 {d['forecast']}명 · 준비 {d['prep']}인분 · 공식 {d['formula']}인분"
          f"{'  ← ' + d['mark'] if d['mark'] else ''}")
    print(f"    {d['comment']}")
print(f"\n저장: {OUT}")
