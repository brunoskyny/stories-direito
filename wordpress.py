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

# "20 a 23 de outubro", "16 até 18 de setembro de 2026" (intervalo contínuo)
_RANGE = re.compile(rf"\b(\d{{1,2}})(?:º)?\s*(?:a|até|-|–)\s*(\d{{1,2}})\s+de\s+{_MES}(?:\s+de\s+(\d{{4}}))?", re.I)
# "4 e 6 de novembro", "21, 22 e 23 de outubro" (lista de dias)
_LIST = re.compile(rf"\b(\d{{1,2}}(?:º)?(?:\s*,\s*\d{{1,2}}(?:º)?)*)\s+e\s+(\d{{1,2}})(?:º)?\s+de\s+{_MES}(?:\s+de\s+(\d{{4}}))?", re.I)
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


def extract_when(text: str, published: date) -> list[tuple[date, date]]:
    """Devolve os blocos de datas do evento: [(início, fim), ...].
    Dias seguidos viram um bloco só (20 a 23/10); dias separados viram blocos
    separados (4 e 6/11 -> dois cards no story)."""
    cands = [(m.start(), "range", m) for m in [_RANGE.search(text)] if m]
    cands += [(m.start(), "list", m) for m in [_LIST.search(text)] if m]
    cands += [(m.start(), "single", m) for m in [_SINGLE.search(text)] if m]
    if not cands:
        return []
    # usa o que aparecer primeiro no texto (o subtítulo costuma trazer a data do evento)
    _, kind, m = min(cands, key=lambda c: (c[0], c[1] != "list", c[1] != "range"))
    if kind == "range":
        mon = _NUM[m[3].lower()]
        y = int(m[4]) if m[4] else _year_for(mon, int(m[1]), published)
        return [(date(y, mon, int(m[1])), date(y, mon, int(m[2])))]
    if kind == "list":
        mon = _NUM[m[3].lower()]
        nums = [int(n) for n in re.findall(r"\d{1,2}", m[1])] + [int(m[2])]
        y = int(m[4]) if m[4] else _year_for(mon, nums[0], published)
        days = sorted({date(y, mon, n) for n in nums})
        blocks, ini, prev = [], days[0], days[0]
        for d in days[1:]:
            if (d - prev).days == 1:
                prev = d
                continue
            blocks.append((ini, prev))
            ini = prev = d
        blocks.append((ini, prev))
        return blocks
    mon = _NUM[m[2].lower()]
    y = int(m[3]) if m[3] else _year_for(mon, int(m[1]), published)
    d = date(y, mon, int(m[1]))
    return [(d, d)]


def section_for(text: str, d: date) -> str:
    """Trecho do texto que fala de um dia específico (ex.: 'Sexta-feira, 6 de novembro – PUC-Rio ...').
    Ignora a primeira menção (o resumo geral) quando houver uma seção própria mais abaixo."""
    mes = [k for k, v in _NUM.items() if v == d.month][0]
    pat = re.compile(rf"\b0?{d.day}(?:º)?\s+de\s+{mes}|\b0?{d.day}/0?{d.month}\b", re.I)
    hits = [m.start() for m in pat.finditer(text)]
    for pos in reversed(hits):  # a seção detalhada costuma ser a última menção
        chunk = text[pos:pos + 400]
        if _LOCAL.search(chunk):
            return chunk
    return ""


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
        local = m[1]
        p = _PLACE.search(local)          # "PUC-Rio, Auditório FB6, ..." -> "Auditório FB6"
        if p:
            return p[1]
        return re.sub(r"\s*\(.*", "", local.split(",")[0]).strip()[:40]  # "FGV Direito Rio (Praia...)" -> "FGV Direito Rio"
    m = _PLACE.search(text)
    if m:
        return m[1]
    return "Online" if _ONLINE.search(text) else ""


_OUTRAS = re.compile(r"\b(FGV|UERJ|UFRJ|UFF|UNIRIO|IBMEC|Mackenzie|OAB|IAB|EMERJ|Tribunal|F[óo]rum)\b", re.I)


def is_at_puc(text: str) -> bool:
    """Decide pelo 'Local:' do evento. Sem 'Local:' na notícia, considera que é na PUC-Rio."""
    m = _LOCAL.search(text)
    if not m:
        return True
    local = m[1]
    if re.search(r"PUC", local, re.I):
        return True
    return not _OUTRAS.search(local)


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
        blocks = extract_when(text, published)
        if not blocks:
            continue
        title = html.unescape(re.sub(r"<[^>]+>", "", p["title"]["rendered"])).strip()
        url = f"{wp.get('public_base', '').rstrip('/')}/noticia/{p['slug']}" if wp.get("public_base") else p["link"]
        for ini, fim in blocks:
            # quando a notícia tem uma seção para o dia (ex.: "Sexta-feira, 6 de novembro – PUC-Rio"),
            # horário e local saem dessa seção; senão, do texto todo
            sec = section_for(text, ini) if len(blocks) > 1 else ""
            if wp.get("somente_puc", True) and not is_at_puc(sec or text):
                continue  # ex.: dia do seminário realizado na FGV
            out.append(Event(
                title=title, day=ini, end=fim if fim != ini else None,
                start=extract_time(sec) or extract_time(text),
                location=extract_place(sec) or extract_place(text),
                url=url,
            ))
    return out
