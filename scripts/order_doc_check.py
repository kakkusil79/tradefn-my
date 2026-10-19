#!/usr/bin/env python3
"""order_doc_check.py — 신규오더 · 서류 요청 점검 한 장 (4일차 실습 C · 「7. 자유 퀘스트」)

받은편지함에서 신규오더 메일과 서류 요청 메일을 코드 규칙으로 골라
  - 신규오더: 주문 금액 · 결제기간 · 선적지를 buyer_profile.csv의 평소 모습과 나란히 놓고 '평소와 다른 점'을 센다
  - 서류 요청: 그 바이어의 미결제 송장(workbench/day4/data/d4_open_inv.csv · paid=N)을 붙인다
1부 판정(멈춤 · 확인 · 기록)은 mail_risk.json에서 읽기만 한다. AI를 부르지 않는다.

쓰는 법 (저장소 맨 위 폴더):
    uv run python scripts/order_doc_check.py            # 1부 AI 결과 기준 → outputs/order_doc_check.html
    uv run python scripts/order_doc_check.py --no-ai    # 1부 --no-ai 결과 기준 → outputs/no_ai/order_doc_check.html
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import mail_bot as mb

OPEN_INV_CSV = mb.ROOT / "workbench/day4/data/d4_open_inv.csv"
ORDER_SIZE_X = 5                                       # 1부 ⑦과 같은 기준 — 월 매출의 5배를 넘으면 '다름'

NEW_ORDER_RE = re.compile(r"\bnew order\b|\border request\b", re.I)
TERMS_RE = re.compile(r"\b(\d{2,3})\s*days?\b", re.I)
SHIP_RE = re.compile(r"\bship (?:it |them |the goods )?to\s+(.+?)\s+instead of\s+([^.\n]+)", re.I)
DOC_KINDS = [                                          # (정규식, 보이는 이름)
    (re.compile(r"\bsurrender\s+B/?L\b", re.I), "surrender B/L 인도"),
    (re.compile(r"\bshipping documents?\b", re.I), "선적서류 발행"),
    (re.compile(r"\bconsignee\b", re.I), "수하인 변경"),
    (re.compile(r"\bbill of lading\b|\bB/L\b", re.I), "B/L"),
]
# 할 일 글은 labs/day4/fraud_signals.md의 ⑦ · ⑪ '할 일' 칸에서 가져왔다
ORDER_ACTION = "권고(사람 승인 전): 한도는 단계적으로 올리고, 대표자 · 감사인 · 사업자 실존을 별도 경로로 확인"
DOC_ACTION = "권고(사람 승인 전): 은행의 입금 확인 전에는 서류를 넘기지 않음"
NO_RISK = "1부 결과 없음 — 확인 필요"


# ---------------------------------------------------------------- 읽기
def read_open_invoices(path: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["paid"].strip().upper() == "N":
                out.setdefault(row["buyer_id"], []).append(row)
    return out


def read_risk(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    return {m["file"]: m for m in json.loads(path.read_text(encoding="utf-8"))["mails"]}


# ---------------------------------------------------------------- 신규오더 — 평소와 다른 점
def order_check(body: str, subject: str, profile: dict | None) -> dict | None:
    m_amt = mb.ORDER_RE.search(body)
    if not (m_amt or NEW_ORDER_RE.search(subject) or NEW_ORDER_RE.search(body)):
        return None
    rows = []
    monthly = float(profile["monthly_sales_usd"]) if profile and profile.get("monthly_sales_usd") else None
    if m_amt:
        amount = float(m_amt.group(1).replace(",", ""))
        if monthly:
            ratio = amount / monthly
            rows.append({"item": "주문 금액", "usual": f"월 매출 약 {monthly:,.0f}달러",
                         "now": f"{amount:,.0f}달러 (월 매출의 {ratio:.1f}배)", "diff": ratio > ORDER_SIZE_X,
                         "quote": mb.sentence_at(body, m_amt.start(), m_amt.end())})
        else:
            rows.append({"item": "주문 금액", "usual": "등록 정보 없음 — 확인 필요", "now": f"{amount:,.0f}달러",
                         "diff": None, "quote": mb.sentence_at(body, m_amt.start(), m_amt.end())})
    m_terms = TERMS_RE.search(body)
    if m_terms:
        days = int(m_terms.group(1))
        usual_days = int(profile["terms_days"]) if profile and profile.get("terms_days") else None
        rows.append({"item": "결제기간", "usual": f"{profile['payment_method']} {usual_days}일" if usual_days else "등록 정보 없음 — 확인 필요",
                     "now": f"{days}일", "diff": (days != usual_days) if usual_days else None,
                     "quote": mb.sentence_at(body, m_terms.start(), m_terms.end())})
    m_ship = SHIP_RE.search(body)
    if m_ship:
        usual_ship = profile["usual_ship_to"] if profile else ""
        usual_city = usual_ship.split(",")[0].strip().lower()
        dest = m_ship.group(1).strip()
        rows.append({"item": "선적지", "usual": usual_ship or "등록 정보 없음 — 확인 필요", "now": dest,
                     "diff": (usual_city not in dest.lower()) if usual_city else None,
                     "quote": mb.sentence_at(body, m_ship.start(), m_ship.end())})
    return {"rows": rows, "diff_count": sum(1 for r in rows if r["diff"])}


# ---------------------------------------------------------------- 서류 요청 — 미결제 송장
def doc_check(body: str, invoices: list[dict], today: str) -> dict | None:
    kinds, quotes = [], []
    for rx, name in DOC_KINDS:
        m = rx.search(body)
        if m and name not in kinds:
            if name == "B/L" and any(k.startswith("surrender") for k in kinds):
                continue                               # surrender B/L과 겹치면 한 번만
            kinds.append(name)
            q = mb.sentence_at(body, m.start(), m.end())
            if q not in quotes:
                quotes.append(q)
    if not kinds:
        return None
    overdue = [r for r in invoices if r["due_date"] < today]
    return {
        "kinds": kinds, "quotes": quotes,
        "open_count": len(invoices), "open_usd": round(sum(float(r["amount_usd"]) for r in invoices), 2),
        "overdue_count": len(overdue), "overdue_usd": round(sum(float(r["amount_usd"]) for r in overdue), 2),
        "oldest_due": min((r["due_date"] for r in invoices), default=""),
    }


# ---------------------------------------------------------------- 한 장 쓰기
EXTRA_CSS = """
.counts.two{grid-template-columns:repeat(2,minmax(0,1fr))}
.count.order{--c:var(--ink)}.count.doc{--c:var(--ink)}
.cmp{border-top:1px solid var(--line);padding:8px 0}
.cmp-h{display:flex;justify-content:space-between;align-items:center;gap:8px;font-weight:700}
.pill{font-size:14px;font-weight:700;border-radius:6px;padding:1px 8px;border:2px solid var(--ink);color:var(--ink);background:var(--card)}
.pill.same{border-color:var(--line);color:var(--sub)}
.cmp-row{font-size:15px}.cmp-row b{color:var(--sub);font-weight:600;margin-right:4px}
.diffsum{font-size:16px;font-weight:700;margin:6px 0}
.inv{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin:8px 0}
.inv div{background:var(--soft);border-radius:8px;padding:6px 8px}
.inv .v{display:block;font-size:20px;font-weight:700}.inv .k{font-size:14px;color:var(--sub)}
"""


def status_tag(risk: dict | None) -> tuple[str, str]:
    """(꼬리표 글, 카드 색 class)"""
    if not risk:
        return NO_RISK, "log"
    tag = f"{risk['status']} · {risk['tier']}" if risk["tier"] else risk["status"]
    return f"1부 판정 {tag}", mb.STATUS_CLASS[risk["status"]]


def card_head(item: dict) -> list[str]:
    e = html.escape
    tag, _ = status_tag(item["risk"])
    out = ['<div class="tags">', f'<span class="tag">{e(tag)}</span>']
    if item["risk"] and item["risk"]["injection"]:
        out.append(f'<span class="tag inj">{e(mb.INJ_TAG)}</span>')
    out += ["</div>", "<dl>",
            f"<dt>바이어</dt><dd>{e(item['buyer_id'])} {e(item['buyer_name'])}</dd>",
            f"<dt>파일</dt><dd>{e(item['file'])}</dd>",
            f"<dt>제목</dt><dd>{e(item['subject'])}</dd>", "</dl>"]
    return out


def callback_block(item: dict, action: str) -> list[str]:
    e = html.escape
    return [f'<div class="callback"><span class="cb-k">콜백 — 등록 번호</span><span class="cb-n">{e(item["callback"])}</span></div>',
            f'<p class="action">{e(action)}</p>']


def order_card(item: dict) -> str:
    e = html.escape
    o = item["order"]
    out = [f'<article class="card {status_tag(item["risk"])[1]}">', *card_head(item),
           f'<p class="diffsum">평소와 다른 점 {o["diff_count"]}개 / 비교 {len(o["rows"])}개</p>']
    for r in o["rows"]:
        pill = ('<span class="pill">다름</span>' if r["diff"] else
                '<span class="pill same">같음</span>' if r["diff"] is False else '<span class="pill same">확인 필요</span>')
        out += ['<div class="cmp">', f'<div class="cmp-h"><span>{e(r["item"])}</span>{pill}</div>',
                f'<div class="cmp-row"><b>평소</b>{e(r["usual"])}</div>',
                f'<div class="cmp-row"><b>이번</b>{e(r["now"])}</div>',
                f'<blockquote>{e(mb.mask_phone(r["quote"]))}</blockquote>', "</div>"]
    out += callback_block(item, ORDER_ACTION) + ["</article>"]
    return "\n".join(out)


def doc_card(item: dict) -> str:
    e = html.escape
    d = item["doc"]
    out = [f'<article class="card {status_tag(item["risk"])[1]}">', *card_head(item),
           f'<p class="diffsum">요청: {e(" · ".join(d["kinds"]))}</p>']
    out += [f'<blockquote>{e(mb.mask_phone(q))}</blockquote>' for q in d["quotes"]]
    out += ['<div class="inv">',
            f'<div><span class="v">{d["open_count"]}건</span><span class="k">미결제 송장</span></div>',
            f'<div><span class="v">{d["open_usd"]:,.0f}달러</span><span class="k">미결제 합계</span></div>',
            f'<div><span class="v">{d["overdue_count"]}건</span><span class="k">기일 지남</span></div>',
            f'<div><span class="v">{d["overdue_usd"]:,.0f}달러</span><span class="k">기일 지난 합계</span></div>',
            "</div>"]
    if d["oldest_due"]:
        out.append(f'<p class="detail">가장 이른 기일 {e(d["oldest_due"])} · 송장 기준 d4_open_inv.csv(paid=N)</p>')
    out += callback_block(item, DOC_ACTION) + ["</article>"]
    return "\n".join(out)


def write_page(path: Path, items: list[dict], source: str, now: str) -> None:
    e = html.escape
    orders = [i for i in items if i["order"]]
    docs = [i for i in items if i["doc"]]
    parts = [
        "<!doctype html>", '<html lang="ko">', "<head>", '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>신규오더 · 서류 요청 점검</title>", f"<style>{mb.BOARD_CSS}{EXTRA_CSS}</style>", "</head>", "<body>", "<main>",
        "<header>", "<h1>신규오더 · 서류 요청 점검</h1>", '<p class="sub">(가상) 한빛정밀(주) 수출팀 공용 메일함</p>',
        f'<div class="meta-line"><span>기준 {e(now)}</span><span>메일 {len(items)}통</span><span>1부 판정 {e(source)}</span></div>',
        "</header>",
        '<p class="band">로봇은 답장 · 송금 · 전달 · 서류 인도를 하지 않습니다</p>',
        '<section class="counts two" aria-label="종류별 메일 수">',
        f'<div class="count order"><span class="n">{len(orders)}</span><span class="k">신규오더</span></div>',
        f'<div class="count doc"><span class="n">{len(docs)}</span><span class="k">서류 요청</span></div>',
        "</section>",
        f"<section><h2>신규오더 — 평소와 다른 점 ({len(orders)})</h2>",
        *([order_card(i) for i in orders] or ['<p class="none">없음</p>']), "</section>",
        f"<section><h2>서류 요청 — 미결제 송장 ({len(docs)})</h2>",
        *([doc_card(i) for i in docs] or ['<p class="none">없음</p>']), "</section>",
        "<footer>",
        f"<p>평소 모습 buyer_profile.csv · 미결제 송장 d4_open_inv.csv · 금액 '다름' = 월 매출의 {ORDER_SIZE_X}배 초과(1부 신호 7과 같은 기준)</p>",
        "<p>고르기 · 비교 · 합계는 코드 · 판정은 1부 결과를 그대로 · 결정은 사람. 모든 조치는 권고(사람 승인 전)입니다.</p>",
        "<p>회사 · 바이어 · 메일 · 번호 · 송장은 모두 가상입니다.</p>", "</footer>",
        "</main>", "</body>", "</html>", "",
    ]
    path.write_text("\n".join(parts), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="신규오더 · 서류 요청 점검 한 장")
    ap.add_argument("--no-ai", action="store_true", help="1부 --no-ai 결과를 기준으로(결과는 outputs/no_ai/)")
    args = ap.parse_args(argv)

    out_dir = mb.OUT_NO_AI if args.no_ai else mb.OUT_AI
    risk = read_risk(out_dir / "mail_risk.json")
    source = ("규칙만(--no-ai)" if args.no_ai else "AI") if risk else NO_RISK
    contacts, profiles = mb.read_csv(mb.CONTACTS_CSV), mb.read_csv(mb.PROFILE_CSV)
    open_inv = read_open_invoices(OPEN_INV_CSV)
    now_dt = datetime.now(mb.KST)
    today = now_dt.strftime("%Y-%m-%d")

    items = []
    for path in mb.inbox_files():
        mail = mb.read_mail(path)
        bid = mb.find_buyer(path, mb.domain_of(mail["sender"])[1], contacts)
        profile = profiles.get(bid)
        contact = contacts.get(bid) or {}
        items.append({
            "file": path.name, "buyer_id": bid, "buyer_name": (contact or profile or {}).get("buyer_name", ""),
            "subject": mail["subject"], "callback": contact.get("phone_on_file") or mb.NO_CALLBACK,
            "risk": risk.get(path.name),
            "order": order_check(mail["body"], mail["subject"], profile),
            "doc": doc_check(mail["body"], open_inv.get(bid, []), today),
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    page = out_dir / "order_doc_check.html"
    write_page(page, items, source, now_dt.strftime("%Y-%m-%d %H:%M KST"))

    for i in items:
        kinds = []
        if i["order"]:
            kinds.append(f"신규오더(다른 점 {i['order']['diff_count']}개)")
        if i["doc"]:
            d = i["doc"]
            kinds.append(f"서류 요청({' · '.join(d['kinds'])} · 미결제 {d['open_count']}건 {d['open_usd']:,.0f}달러 · 기일 지남 {d['overdue_count']}건)")
        tag = status_tag(i["risk"])[0]
        print(f"{i['file']} · {i['buyer_id']} · {tag} · {' / '.join(kinds) or '-'}")
    print(f"결과: {page.relative_to(mb.ROOT).as_posix()}")
    print(f"메일 {len(items)}통 · 신규오더 {sum(1 for i in items if i['order'])} · 서류 요청 {sum(1 for i in items if i['doc'])} · 1부 판정 {source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
