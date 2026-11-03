"""Leitura dos eventos publicados no site do departamento."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

MESES = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}


@dataclass
class Event:
    title: str
    day: date
    start: time | None = None
    location: str = ""
    url: str = ""
    end: date | None = None   # último dia, quando o evento dura vários dias


# ---------------------------------------------------------------- datas
def parse_date_pt(text: str, ref_year: int) -> tuple[date | None, time | None]:
    """Entende '2026-11-12T14:00', '12/11/2026', '12/11', '12 de novembro de 2026',
    '12 nov', 'qui, 12 de nov · 14h30' etc."""
    if not text:
        return None, None
    t = text.strip().lower()

    # ISO (atributo datetime / JSON-LD)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})(?:[t ](\d{2}):(\d{2}))?", t)
    if m:
        d = date(int(m[1]), int(m[2]), int(m[3]))
        hh = time(int(m[4]), int(m[5])) if m[4] else None
        return d, hh

    d = None
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
    if m:
        y = int(m[3]) if m[3] else ref_year
        y = y + 2000 if y < 100 else y
        d = date(y, int(m[2]), int(m[1]))
    else:
        m = re.search(r"\b(\d{1,2})\s*(?:de\s+)?([a-zç]{3})[a-zç]*\.?(?:\s*(?:de\s+)?(\d{4}))?", t)
        if m and m[2] in MESES:
            y = int(m[3]) if m[3] else ref_year
            d = date(y, MESES[m[2]], int(m[1]))

    hh = None
    m = re.search(r"\b(\d{1,2})\s*(?:h|:)\s*(\d{2})?\b", t)
    if m and d:
        h, mi = int(m[1]), int(m[2] or 0)
        if h < 24 and mi < 60:
            hh = time(h, mi)
    return d, hh


# ---------------------------------------------------------------- leitores
def _from_jsonld(soup: BeautifulSoup, ref_year: int) -> list[Event]:
    out: list[Event] = []

    def walk(node):
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            typ = node.get("@type")
            typs = typ if isinstance(typ, list) else [typ]
            if any(isinstance(x, str) and x.endswith("Event") for x in typs):
                d, hh = parse_date_pt(str(node.get("startDate", "")), ref_year)
                if d and node.get("name"):
                    loc = node.get("location") or {}
                    loc = loc.get("name", "") if isinstance(loc, dict) else str(loc)
                    out.append(Event(str(node["name"]).strip(), d, hh, loc, str(node.get("url", ""))))
            for v in node.values():
                if isinstance(v, (dict, list)):
                    walk(v)

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            walk(json.loads(tag.string or ""))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def _from_ical(text: str) -> list[Event]:
    out: list[Event] = []
    text = re.sub(r"\r?\n[ \t]", "", text)  # desdobra linhas
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        fields = {}
        for line in block.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fields[k.split(";")[0].upper()] = v.strip()
        m = re.match(r"(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2}))?", fields.get("DTSTART", ""))
        if not m or not fields.get("SUMMARY"):
            continue
        d = date(int(m[1]), int(m[2]), int(m[3]))
        hh = time(int(m[4]), int(m[5])) if m[4] else None
        out.append(Event(fields["SUMMARY"].replace("\\,", ","), d, hh,
                         fields.get("LOCATION", "").replace("\\,", ","), fields.get("URL", "")))
    return out


def _from_css(soup: BeautifulSoup, cfg: dict, ref_year: int, base_url: str) -> list[Event]:
    out: list[Event] = []
    for item in soup.select(cfg["item"]):
        def pick(sel):
            return item.select_one(sel) if sel else None

        t_el, d_el = pick(cfg.get("title")), pick(cfg.get("date"))
        if not t_el or not d_el:
            continue
        raw = d_el.get("datetime") or d_el.get_text(" ", strip=True)
        d, hh = parse_date_pt(raw, ref_year)
        if not d:
            continue
        tm_el = pick(cfg.get("time"))
        if tm_el and not hh:
            _, hh = parse_date_pt("01/01 " + tm_el.get_text(" ", strip=True), ref_year)
        loc_el, a_el = pick(cfg.get("location")), pick(cfg.get("link"))
        href = a_el.get("href", "") if a_el else ""
        out.append(Event(
            t_el.get_text(" ", strip=True), d, hh,
            loc_el.get_text(" ", strip=True) if loc_el else "",
            requests.compat.urljoin(base_url, href) if href else "",
        ))
    return out


def fetch_events(cfg: dict, today: date) -> list[Event]:
    if cfg.get("source_type") == "wordpress":
        from wordpress import fetch_wordpress
        return fetch_wordpress(cfg, today)
    url = cfg["events_url"]
    resp = requests.get(url, timeout=30, headers={"User-Agent": "dsi-story-bot/1.0"})
    resp.raise_for_status()
    if "charset" not in resp.headers.get("content-type", "").lower():
        resp.encoding = resp.apparent_encoding or "utf-8"
    kind = cfg.get("source_type", "auto")
    body = resp.text

    if kind == "ical" or (kind == "auto" and "BEGIN:VCALENDAR" in body[:500]):
        return _from_ical(body)

    soup = BeautifulSoup(body, "html.parser")
    if kind in ("auto", "jsonld"):
        evs = _from_jsonld(soup, today.year)
        if evs or kind == "jsonld":
            return evs
    if kind == "auto":  # link para .ics na página?
        a = soup.find("a", href=re.compile(r"\.ics(\?|$)|ical", re.I))
        if a:
            r = requests.get(requests.compat.urljoin(url, a["href"]), timeout=30)
            if r.ok and "BEGIN:VCALENDAR" in r.text:
                return _from_ical(r.text)
    return _from_css(soup, cfg["css"], today.year, url)


def week_bounds(today: date) -> tuple[date, date]:
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


def events_this_week(events: list[Event], today: date) -> list[Event]:
    ini, fim = week_bounds(today)
    seen, out = set(), []
    for e in sorted(events, key=lambda e: (e.day, e.start or time(0))):
        key = (e.title.lower(), e.day)
        last = e.end or e.day
        if e.day <= fim and last >= ini and key not in seen:  # sobrepõe a semana
            seen.add(key)
            out.append(e)
    return out


def now_local(tz: str) -> datetime:
    return datetime.now(ZoneInfo(tz))
