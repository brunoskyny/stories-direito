"""Gera a arte do story (1080x1920, JPEG — único formato aceito pela API)."""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from events import Event

W, H = 1080, 1920
DIAS = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

_FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "assets"]


def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for d in _FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _wrap(draw, text, font, max_w, max_lines):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while draw.textlength(lines[-1] + "…", font=font) > max_w and " " in lines[-1]:
            lines[-1] = lines[-1].rsplit(" ", 1)[0]
        lines[-1] += "…"
    return lines


def render_story(events: list[Event], cfg: dict, out_path: Path, page: str = "") -> Path:
    s = cfg["story"]
    top, bot = _hex(s["background_top"]), _hex(s["background_bottom"])
    accent, fg = _hex(s["accent"]), _hex(s["text"])

    img = Image.new("RGB", (W, H))
    px = ImageDraw.Draw(img)
    for y in range(H):  # degradê vertical
        k = y / H
        px.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * k) for i in range(3)))
    d = ImageDraw.Draw(img)

    # Área segura: o Instagram cobre ~250px no topo e embaixo com a interface
    y = 270
    logo = s.get("logo_path")
    if logo and Path(logo).exists():
        lg = Image.open(logo).convert("RGBA")
        lg.thumbnail((440, 230))
        img.paste(lg, ((W - lg.width) // 2, y), lg)
        y += lg.height + 40

    f_head = _font(True, 64)
    d.text((W // 2, y), s["header"], font=f_head, fill=fg, anchor="ma")
    y += 90
    d.rectangle([(W // 2 - 80, y), (W // 2 + 80, y + 8)], fill=accent)
    y += 50
    if s.get("subheader"):
        d.text((W // 2, y), s["subheader"], font=_font(False, 36), fill=fg, anchor="ma")
        y += 60
    if page:
        d.text((W // 2, y), page, font=_font(False, 34), fill=fg, anchor="ma")
        y += 50

    f_day, f_num = _font(True, 34), _font(True, 64)
    f_title, f_meta = _font(True, 44), _font(False, 34)
    card_x0, card_x1 = 70, W - 70
    avail = (H - 330) - y
    card_h = min(300, (avail - 30 * (len(events) - 1)) // max(len(events), 1))

    for e in events:
        d.rounded_rectangle([(card_x0, y), (card_x1, y + card_h)], radius=32,
                            fill=None, outline=fg, width=3)
        # selo da data
        bx0, bx1 = card_x0 + 28, card_x0 + 28 + 160
        by0, by1 = y + 28, y + card_h - 28
        d.rounded_rectangle([(bx0, by0), (bx1, by1)], radius=22, fill=accent)
        cy = (by0 + by1) // 2
        d.text(((bx0 + bx1) // 2, cy - 48), DIAS[e.day.weekday()], font=f_day, fill=top, anchor="mm")
        d.text(((bx0 + bx1) // 2, cy + 6), f"{e.day.day:02d}", font=f_num, fill=top, anchor="mm")
        d.text(((bx0 + bx1) // 2, cy + 56), MESES[e.day.month - 1], font=f_day, fill=top, anchor="mm")

        tx, tw = bx1 + 36, card_x1 - 30 - (bx1 + 36)
        periodo = f"até {e.end.day:02d}/{e.end.month:02d}" if e.end else ""
        meta = " · ".join(x for x in [periodo, e.start.strftime("%Hh%M").replace("h00", "h") if e.start else "",
                                      e.location] if x)
        max_lines = 3
        lines = _wrap(d, e.title, f_title, tw, max_lines)
        block_h = len(lines) * 54 + (48 if meta else 0)
        ty = y + (card_h - block_h) // 2
        for ln in lines:
            d.text((tx, ty), ln, font=f_title, fill=fg)
            ty += 54
        if meta:
            meta_ln = _wrap(d, meta, f_meta, tw, 1)[0]
            d.text((tx, ty + 6), meta_ln, font=f_meta, fill=accent)
        y += card_h + 30

    d.text((W // 2, H - 290), s["footer"], font=_font(False, 36), fill=fg, anchor="ma")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=92)
    return out_path
