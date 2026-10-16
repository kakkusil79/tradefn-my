"""3일차 실습 C: 한빛식당 밥 예보 페이지 (workbench/day3/outputs/hanbit_lunch.html)

실행: uv run python scripts/lunch_page.py
입력: workbench/day3/outputs/lunch_clean.csv · labs/day3/lab-c/nutritionist_memo.md (읽기만)
페이지는 손으로 고치지 않는다 — 이 스크립트가 계산해서 쓴다(같은 입력이면 같은 페이지).
구역: 머리 → 영양사님 감 검증
(가상) 한빛정밀(주) 본사 구내식당 '한빛식당'의 가상 기록이다.
"""
import html
import json
import re
import sys
from pathlib import Path

import pandas as pd

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

# --- 화면에 넘길 데이터(JSON) -----------------------------------------------------------
def public(obj):
    """'_'로 시작하는 계산용 값은 빼고 넘긴다."""
    if isinstance(obj, dict):
        return {k: public(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [public(v) for v in obj]
    return obj


period = f"{df['날짜'].min()} ~ {df['날짜'].max()}"
DATA = {"beliefs": public(cards), "payday": public(payday), "colors": {"accent": ACCENT, "warn": WARN, "gray": GRAY}}


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
print(f"\n저장: {OUT}")
