from __future__ import annotations

import calendar
import html
import json
import re
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .config import Config
from .database import Database


CSS = """
:root {
  color-scheme: light;
  --ink:#15211b; --paper:#f3f1e8; --sheet:#fffdf6; --line:#d9d6ca;
  --muted:#68716b; --green:#1f6048; --lime:#d9f26a; --orange:#ee6c3b;
  --shadow:0 24px 70px rgba(35,45,39,.10);
}
* { box-sizing:border-box }
html { background:var(--paper) }
body { margin:0; color:var(--ink); font:16px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif }
a { color:inherit; text-decoration:none }
.shell { width:min(1180px,calc(100% - 40px)); margin:auto }
.site-header { display:flex; align-items:center; justify-content:space-between; padding:28px 0 18px; border-bottom:1px solid var(--line) }
.brand { display:flex; align-items:center; gap:11px; font-weight:800; letter-spacing:-.03em }
.brand-mark { width:13px; height:13px; border-radius:50%; background:var(--orange); box-shadow:18px 0 0 var(--lime) }
.brand span { margin-left:18px }
.site-header nav { display:flex; gap:20px; color:var(--muted); font-size:.88rem }
.eyebrow { color:var(--green); font-size:.72rem; font-weight:800; letter-spacing:.16em; text-transform:uppercase }
.hero { display:grid; grid-template-columns:minmax(0,1.45fr) minmax(260px,.55fr); gap:44px; padding:70px 0 54px }
.hero h1,.day-title { font-family:Georgia,'Times New Roman',serif; font-weight:500; letter-spacing:-.055em; line-height:.94; margin:12px 0 22px }
.hero h1 { font-size:clamp(3.8rem,8vw,7.4rem) }
.hero-copy { max-width:720px; font-size:1.14rem; color:#465049 }
.latest-card { align-self:end; background:var(--ink); color:white; padding:28px; border-radius:2px; box-shadow:var(--shadow) }
.latest-card .eyebrow { color:var(--lime) }
.latest-card h2 { font-family:Georgia,serif; font-weight:500; font-size:1.55rem; line-height:1.15; margin:12px 0 }
.latest-card p { color:#cbd2cd; margin:0 0 22px }
.button { display:inline-flex; align-items:center; gap:9px; background:var(--lime); color:var(--ink); padding:10px 14px; font-weight:800; font-size:.83rem }
.section-head { display:flex; justify-content:space-between; align-items:end; gap:20px; margin:20px 0 }
.section-head h2 { margin:0; font:500 clamp(2rem,4vw,3.2rem)/1 Georgia,serif; letter-spacing:-.04em }
.month-nav { display:flex; align-items:center; gap:8px }
.month-nav a { border:1px solid var(--line); background:var(--sheet); padding:7px 11px; font-weight:700 }
.calendar { background:var(--line); border:1px solid var(--line); display:grid; grid-template-columns:repeat(7,minmax(0,1fr)); gap:1px; box-shadow:var(--shadow); margin-bottom:80px }
.weekday { min-height:42px; padding:12px 14px; background:var(--ink); color:#dfe5e1; font-size:.7rem; text-transform:uppercase; letter-spacing:.13em }
.day { min-height:150px; padding:13px; background:var(--sheet); position:relative }
.day.other { background:#ebe9df; color:#9a9e9a }
.day-number { font:500 1.22rem Georgia,serif }
.day.today .day-number { display:inline-grid; place-items:center; width:29px; height:29px; border-radius:50%; background:var(--orange); color:white }
.edition { display:block; height:100%; margin:-13px; padding:13px; transition:background .16s ease,transform .16s ease }
.edition:hover { background:#f7f8df; transform:translateY(-2px) }
.edition-meta { display:block; color:var(--green); font-size:.7rem; font-weight:800; text-transform:uppercase; letter-spacing:.08em; margin-top:25px }
.edition-title { display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; font:500 .88rem/1.35 Georgia,serif; margin-top:7px }
.day.failed::after { content:'retry pending'; color:var(--orange); font-size:.68rem; position:absolute; bottom:11px; left:13px }
.empty-state { grid-column:1/-1; background:var(--sheet); padding:50px; text-align:center }
.day-page { max-width:980px; margin:0 auto; padding:58px 0 90px }
.back { display:inline-flex; gap:8px; color:var(--green); font-size:.84rem; font-weight:800; margin-bottom:36px }
.day-title { font-size:clamp(3.4rem,8vw,6.8rem); max-width:850px }
.day-deck { font:500 clamp(1.25rem,2.5vw,1.75rem)/1.4 Georgia,serif; max-width:820px; color:#3d4841; margin-bottom:46px }
.rule-label { display:grid; grid-template-columns:auto 1fr; align-items:center; gap:14px; color:var(--green); font-size:.72rem; font-weight:800; letter-spacing:.14em; text-transform:uppercase; margin:48px 0 20px }
.rule-label::after { content:''; height:1px; background:var(--line) }
.story-list { list-style:none; padding:0; margin:0; counter-reset:story }
.story-list li { counter-increment:story; display:grid; grid-template-columns:48px 1fr; gap:18px; padding:20px 0; border-bottom:1px solid var(--line); font:500 clamp(1.05rem,2vw,1.35rem)/1.35 Georgia,serif }
.story-list li::before { content:counter(story,decimal-leading-zero); color:var(--orange); font:800 .76rem/1.7 Inter,sans-serif; letter-spacing:.08em }
.story-link { display:flex; justify-content:space-between; gap:18px }
.story-link:hover { color:var(--green); text-decoration:underline; text-decoration-thickness:1px; text-underline-offset:4px }
.external { color:var(--green); font:800 .82rem Inter,sans-serif; flex:none }
.topics { display:grid; grid-template-columns:repeat(3,1fr); gap:12px }
.topic { background:var(--sheet); border:1px solid var(--line); padding:20px; min-height:150px }
.topic-head { display:flex; justify-content:space-between; gap:10px; font-weight:850 }
.topic p { color:var(--muted); margin:25px 0 0; font-size:.9rem }
.sources { display:grid; gap:10px }
details { background:var(--sheet); border:1px solid var(--line) }
summary { cursor:pointer; list-style:none; padding:18px 20px; display:grid; grid-template-columns:1fr auto auto; gap:14px; align-items:center }
summary::-webkit-details-marker { display:none }
summary::after { content:'+'; color:var(--green); font-size:1.3rem }
details[open] summary::after { content:'−' }
.source-title { font-weight:850 }
.source-sender { display:block; color:var(--muted); font-size:.75rem; font-weight:500; overflow:hidden; text-overflow:ellipsis }
.source-body { padding:0 20px 22px; border-top:1px solid var(--line); color:#3f4943 }
.source-body ul { margin-bottom:0 }
.source-links { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin-top:18px }
.source-links a { border:1px solid var(--line); padding:9px 11px; color:var(--green); font-size:.8rem; font-weight:750; overflow:hidden; text-overflow:ellipsis; white-space:nowrap }
.source-links a:hover { background:#f0f6cf }
.day-nav { display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:55px }
.day-nav a { border-top:2px solid var(--ink); padding-top:13px; font-weight:800 }
.day-nav a:last-child { text-align:right }
.status-page { text-align:center; padding:18vh 20px }
.status-page h1 { font:500 4rem/1 Georgia,serif; margin:12px }
footer { border-top:1px solid var(--line); padding:24px 0 45px; color:var(--muted); font-size:.78rem; display:flex; justify-content:space-between }
@media(max-width:800px) {
  .hero { grid-template-columns:1fr; padding-top:48px }.latest-card { align-self:auto }
  .calendar { grid-template-columns:repeat(7,minmax(0,1fr)) }
  .weekday { display:block; min-height:auto; padding:8px 1px; text-align:center; font-size:.52rem }
  .day,.day.other { display:block; min-height:54px; padding:7px }
  .day-number { font-size:.9rem }.day.today .day-number { width:23px; height:23px }
  .edition { margin:-7px; padding:7px; background:#f0f6cf; position:relative }
  .edition::after { content:''; position:absolute; width:7px; height:7px; border-radius:50%; background:var(--green); left:8px; bottom:7px }
  .edition-meta,.edition-title { display:none }.topics,.source-links { grid-template-columns:1fr }
  .site-header nav { display:none }.day-page { padding-top:36px }
}
"""


def _e(value: Any) -> str:
    return html.escape(str(value or ""))


_MATCH_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "with", "from",
    "new", "its", "at", "by", "as", "is", "are", "amid", "into", "this", "that",
}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in _MATCH_STOPWORDS
    }


def _best_link(story: str, links: list[dict[str, str]]) -> dict[str, str] | None:
    story_tokens = _tokens(story)
    if not story_tokens:
        return None
    best: dict[str, str] | None = None
    best_score = 0.0
    for link in links:
        label_tokens = _tokens(link.get("label", ""))
        if not label_tokens:
            continue
        overlap = len(story_tokens & label_tokens)
        score = overlap / max(1, min(len(story_tokens), len(label_tokens)))
        if overlap >= 2 and score > best_score:
            best, best_score = link, score
    return best if best_score >= 0.28 else None


def _layout(content: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <meta name="robots" content="noindex,nofollow"><title>Mail digest</title>
    <style>{CSS}</style></head><body><div class="shell">
    <header class="site-header"><a class="brand" href="/"><i class="brand-mark"></i><span>Signal / Tech Brief</span></a>
    <nav><a href="/">Calendar</a><span>Local AI · Private</span></nav></header>
    {content}<footer><span>Generated locally with qwen3:4b</span><span>Proton Mail Bridge · Read only</span></footer>
    </div></body></html>"""


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + month - 1 + delta
    return index // 12, index % 12 + 1


def _parse_month(value: str | None, fallback: date) -> tuple[int, int]:
    if not value:
        return fallback.year, fallback.month
    try:
        parsed = datetime.strptime(value, "%Y-%m")
        return parsed.year, parsed.month
    except ValueError:
        return fallback.year, fallback.month


def render_calendar(database: Database, month_value: str | None = None) -> str:
    latest = database.latest_dashboard()
    latest_date = date.fromisoformat(latest["run"]["digest_date"]) if latest else date.today()
    year, month = _parse_month(month_value, latest_date)
    entries = {row["digest_date"]: row for row in database.calendar_month(year, month)}
    previous = _shift_month(year, month, -1)
    following = _shift_month(year, month, 1)
    latest_card = ""
    if latest and latest["digest"]:
        digest = latest["digest"]
        headline = digest["highlights"][0] if digest["highlights"] else digest["overview"]
        latest_card = f"""<aside class="latest-card"><div class="eyebrow">Latest edition · {_e(latest['run']['digest_date'])}</div>
        <h2>{_e(headline)}</h2><p>{_e(digest['overview'])}</p>
        <a class="button" href="/day/{_e(latest['run']['digest_date'])}">Read today’s brief <span>→</span></a></aside>"""
    else:
        latest_card = "<aside class='latest-card'><div class='eyebrow'>First edition pending</div><h2>Your tech signal will appear here.</h2></aside>"

    cells: list[str] = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
        for current in week:
            classes = ["day"]
            if current.month != month:
                classes.append("other")
            if current == date.today():
                classes.append("today")
            entry = entries.get(current.isoformat())
            if entry and entry["status"] == "completed":
                headline = entry["highlights"][0] if entry["highlights"] else entry.get("overview", "Daily tech brief")
                content = f"""<a class="edition" href="/day/{current.isoformat()}"><span class="day-number">{current.day}</span>
                <span class="edition-meta">{_e(entry['email_count'])} source{'s' if entry['email_count'] != 1 else ''}</span>
                <span class="edition-title">{_e(headline)}</span></a>"""
            else:
                if entry and entry["status"] == "failed":
                    classes.append("failed")
                content = f"<span class='day-number'>{current.day}</span>"
            cells.append(f"<div class='{' '.join(classes)}'>{content}</div>")

    weekdays = "".join(f"<div class='weekday'>{name}</div>" for name in calendar.day_abbr)
    content = f"""
    <section class="hero"><div><div class="eyebrow">Your newsletters, distilled daily</div>
    <h1>Less inbox.<br>More signal.</h1><p class="hero-copy">A private, locally generated briefing of the technology stories worth carrying into your day.</p></div>{latest_card}</section>
    <section><div class="section-head"><div><div class="eyebrow">Archive</div><h2>{calendar.month_name[month]} {year}</h2></div>
    <div class="month-nav"><a aria-label="Previous month" href="/?month={previous[0]:04d}-{previous[1]:02d}">←</a>
    <a aria-label="Next month" href="/?month={following[0]:04d}-{following[1]:02d}">→</a></div></div>
    <div class="calendar">{weekdays}{''.join(cells)}</div></section>"""
    return _layout(content)


def render_day(database: Database, target: date) -> str | None:
    data = database.dashboard_for_date(target)
    if not data or not data["digest"]:
        return None
    run, digest, messages = data["run"], data["digest"], data["messages"]
    all_links = [link for message in messages for link in message.get("links", [])]
    story_rows = []
    for item in digest["highlights"]:
        match = _best_link(item, all_links)
        if match:
            story_rows.append(
                f"<li><a class='story-link' href='{_e(match['url'])}' target='_blank' rel='noopener noreferrer'>"
                f"<span>{_e(item)}</span><span class='external' aria-hidden='true'>↗</span></a></li>"
            )
        else:
            story_rows.append(f"<li>{_e(item)}</li>")
    stories = "".join(story_rows)
    if not stories:
        stories = "<li>No major stories were extracted.</li>"
    topics = "".join(
        f"<article class='topic'><div class='topic-head'><span>{_e(item['name'])}</span><span>{_e(item['count'])}</span></div><p>{_e(item['summary'])}</p></article>"
        for item in digest["categories"]
    ) or "<article class='topic'><div class='topic-head'>Uncategorized</div></article>"
    sources = ""
    for message in messages:
        points = "".join(f"<li>{_e(point)}</li>" for point in message["action_items"])
        source_links = "".join(
            f"<a href='{_e(link['url'])}' target='_blank' rel='noopener noreferrer' title='{_e(link['label'])}'>{_e(link['label'])} ↗</a>"
            for link in message.get("links", [])[:30]
        )
        sources += f"""<details><summary><span><span class="source-title">{_e(message['subject'])}</span>
        <span class="source-sender">{_e(message['sender'])}</span></span><span>{_e(message['category'])}</span></summary>
        <div class="source-body"><p>{_e(message['summary'])}</p>{f'<ul>{points}</ul>' if points else ''}
        {f'<div class="source-links">{source_links}</div>' if source_links else ''}</div></details>"""
    previous, following = database.adjacent_completed_dates(target)
    previous_link = f"<a href='/day/{previous}'>← Previous edition</a>" if previous else "<span></span>"
    following_link = f"<a href='/day/{following}'>Next edition →</a>" if following else "<span></span>"
    pretty_date = target.strftime("%A, %B %-d")
    content = f"""<main class="day-page"><a class="back" href="/?month={target:%Y-%m}">← Back to calendar</a>
    <div class="eyebrow">Daily edition · {run['email_count']} source{'s' if run['email_count'] != 1 else ''}</div>
    <h1 class="day-title">{_e(pretty_date)}</h1><p class="day-deck">{_e(digest['overview'])}</p>
    <div class="rule-label">Top stories</div><ol class="story-list">{stories}</ol>
    <div class="rule-label">Topic map</div><div class="topics">{topics}</div>
    <div class="rule-label">Source newsletters</div><div class="sources">{sources or '<p>No source messages.</p>'}</div>
    <nav class="day-nav">{previous_link}{following_link}</nav></main>"""
    return _layout(content)


def render_not_found() -> str:
    return _layout("<main class='status-page'><div class='eyebrow'>404</div><h1>No edition here</h1><p>Return to the calendar to choose an available day.</p><a class='button' href='/'>Open calendar →</a></main>")


class MailDigestServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_handler(database: Database) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "MailDigest/0.2"

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            if parsed.path == "/":
                month = parse_qs(parsed.query).get("month", [None])[0]
                self._send(render_calendar(database, month), "text/html; charset=utf-8")
                return
            if parsed.path.startswith("/day/"):
                try:
                    target = date.fromisoformat(parsed.path.removeprefix("/day/"))
                except ValueError:
                    self._send(render_not_found(), "text/html; charset=utf-8", HTTPStatus.NOT_FOUND)
                    return
                page = render_day(database, target)
                self._send(page or render_not_found(), "text/html; charset=utf-8", HTTPStatus.OK if page else HTTPStatus.NOT_FOUND)
                return
            if parsed.path == "/healthz":
                self._send(json.dumps({"status": "ok"}), "application/json")
                return
            self._send(render_not_found(), "text/html; charset=utf-8", HTTPStatus.NOT_FOUND)

        def _send(self, content: str, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            payload = content.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def create_server(config: Config, database: Database) -> ThreadingHTTPServer:
    return MailDigestServer((config.host, config.port), make_handler(database))
