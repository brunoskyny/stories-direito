"""Leitor para o site do Departamento de Direito (WordPress headless em api.projetosjur.com).

As notícias não têm campos estruturados de evento: a data, o horário e o local
estão escritos no texto ("na quarta-feira, 4 de novembro, às 10h ... Local: Auditório FB8").
Por isso este módulo:
  1. busca as notícias recentes pela API REST do WordPress;
  2. mantém só as das categorias de evento (palestra, seminário, evento...);
  3. extrai do texto a data (ou período), o horário e o local.
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime, time, timedelta

import requests

from events import MESES, Event

_MES = r"(janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)"
_NUM = {k: MESES[k[:3]] for k in ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
                                    "agosto", "setembro", "outubro", "novembro", "dezembro"]}
_NUM["marco"] = 3

# "20 a 23 de outubro", "dias 20 e 21 de outubro", "16 a 18 de setembro de 2026"
_RANGE = re.compile(rf"\b(\d{{1,2}})(?:º)?\s*(?:a|e|até|-|–)\s*(\d{{1,2}})\s+de\s+{_MES}(?:\s+de\s+(\d{{4}}))?", re.I)
# "4 de novembro", "1º de dezembro de 2026"
_SINGLE = re.compile(rf"\b(\d{{1,2}})(?:º)?\s+de\s+{_MES}(?:\s+de\s+(\d{{4}}))?", re.I)
# "às 10h", "das 11h às 13h", "a partir das 9h", "19h30", "14:00"
_TIME = re.compile(r"\b(?:às|as|das|a partir das)\s+(\d{1,2})\s*(?:h|:)\s*(\d{2})?|\b(\d{1,2})h(\d{2})?\b", re.I)
_LOCAL = re.compile(r"\bLocal:\s*([^\n.;]+)", re.I)
_PLACE = re.compile(r"\b((?:Audit[óo]rio|Sala|Laborat[óo]rio|Anfiteatro)\s+[A-Z0-9][\w\-]*)", re.I)
_ONLINE = re.compile(r"\b(on-?line|youtube|zoom|google meet|transmiss[ãa]o ao vivo)\b", re.I)


def _plain(raw: str) -> str:
    txt = re.sub(r"<(br|/p|/h\d|/li|/div)[^>]*>", "\n", raw, flags=re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    return re.sub(r"[ \t ]+", " ", html.unescape(txt)).strip()


def _year_for(month: int, day: int, published: date) -> int:
    """Evento sem ano: escolhe o ano que deixa a data mais perto (e depois) da publicação."""
    y = published.year
    if date(y, month, day) < published - timedelta(days=60):
        y += 1
    return y


def extract_when(text: str, published: date) -> tuple[date, date] | None:
    m = _RANGE.search(text)
    s = _SINGLE.search(text)
    # usa o que aparecer primeiro no texto (o subtítulo costuma trazer a data do evento)
    if m and (not s or m.start() <= s.start()):
        mon = _NUM[m[3].lower()]
        y = int(m[4]) if m[4] else _year_for(mon, int(m[1]), published)
        return date(y, mon, int(m[1])), date(y, mon, int(m[2]))
    if s:
        mon = _NUM[s[2].lower()]
        y = int(s[3]) if s[3] else _year_for(mon, int(s[1]), published)
        d = date(y, mon, int(s[1]))
        return d, d
    return None


def extract_time(text: str) -> time | None:
    m = _TIME.search(text)
    if not m:
        return None
    h, mi = (m[1], m[2]) if m[1] else (m[3], m[4])
    h, mi = int(h), int(mi or 0)
    return time(h, mi) if h < 24 and mi < 60 else None


def extract_place(text: str) -> str:
    m = _LOCAL.search(text)
    if m:
        return m[1].split(",")[0].strip()[:40]
    m = _PLACE.search(text)
    if m:
        return m[1]
    return "Online" if _ONLINE.search(text) else ""


def fetch_wordpress(cfg: dict, today: date) -> list[Event]:
    wp = cfg["wordpress"]
    api = wp["api_url"].rstrip("/")
    ua = {"User-Agent": "story-bot/1.0"}

    cats = requests.get(f"{api}/categories", params={"per_page": 100, "_fields": "id,slug"},
                        headers=ua, timeout=30).json()
    wanted = {c["id"] for c in cats if c["slug"] in set(wp["event_categories"])}

    since = (today - timedelta(days=wp.get("lookback_days", 45))).isoformat() + "T00:00:00"
    posts = requests.get(f"{api}/posts", headers=ua, timeout=30, params={
        "per_page": 50, "after": since, "orderby": "date", "order": "desc",
        "_fields": "id,date,link,slug,title,content,categories",
    })
    posts.raise_for_status()

    out: list[Event] = []
    for p in posts.json():
        if wanted and not (set(p.get("categories", [])) & wanted):
            continue
        text = _plain(p["content"]["rendered"])
        published = datetime.fromisoformat(p["date"]).date()
        when = extract_when(text, published)
        if not when:
            continue
        ini, fim = when
        # horário e local: procura primeiro perto da data, depois no texto todo
        out.append(Event(
            title=html.unescape(re.sub(r"<[^>]+>", "", p["title"]["rendered"])).strip(),
            day=ini, end=fim if fim != ini else None,
            start=extract_time(text), location=extract_place(text),
            url=f"{wp.get('public_base', '').rstrip('/')}/noticia/{p['slug']}" if wp.get("public_base") else p["link"],
        ))
    return out
