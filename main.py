"""Robô semanal de stories.

  python main.py render   -> lê o site e gera as artes da semana em out/
                             (se não houver evento, não gera nada)
  python main.py publish  -> publica no Instagram as artes listadas em out/manifest.json
  python main.py refresh  -> renova o token do Instagram (roda toda semana, com ou sem evento)

Variáveis de ambiente usadas no publish:
  IG_ACCESS_TOKEN, IMAGE_BASE_URL (endereço público onde out/ foi hospedado)
  IG_USER_ID é opcional: se vazio, é descoberto pelo próprio token
Opcionais: TODAY=AAAA-MM-DD (simula outra data), DRY_RUN=1 (não publica)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from events import events_this_week, fetch_events, now_local, week_bounds  # noqa: E402
from instagram import InstagramError, publish_story, refresh_token, resolve_user_id  # noqa: E402
from render import render_story  # noqa: E402

_HERE = Path(__file__).resolve().parent
ROOT = _HERE if (_HERE / "config.yaml").exists() else _HERE.parent  # funciona com ou sem a pasta src/
OUT = ROOT / "out"


def load_cfg() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def cmd_render(cfg: dict) -> None:
    today = date.fromisoformat(os.environ["TODAY"]) if os.environ.get("TODAY") \
        else now_local(cfg["timezone"]).date()
    ini, fim = week_bounds(today)
    print(f"Semana: {ini:%d/%m} a {fim:%d/%m/%Y}")

    evs = events_this_week(fetch_events(cfg, today), today)
    OUT.mkdir(exist_ok=True)
    manifest = OUT / "manifest.json"
    if not evs:
        print("Nenhum evento nesta semana — nada será publicado.")
        manifest.write_text("[]")
        _gh_output("has_events", "false")
        return

    for e in evs:
        print(f"  • {e.day:%d/%m} {e.start or ''} {e.title}")
    n = cfg["story"]["max_events_per_story"]
    chunks = [evs[i:i + n] for i in range(0, len(evs), n)]
    files = []
    for i, chunk in enumerate(chunks, 1):
        name = f"story-{ini:%Y%m%d}-{i}.jpg"
        page = f"{i}/{len(chunks)}" if len(chunks) > 1 else ""
        render_story(chunk, cfg, OUT / name, page)
        files.append(name)
    manifest.write_text(json.dumps(files))
    print(f"Gerado(s): {', '.join(files)}")
    _gh_output("has_events", "true")


def cmd_publish(cfg: dict) -> None:
    files = json.loads((OUT / "manifest.json").read_text())
    if not files:
        print("Nada a publicar.")
        return
    base = os.environ["IMAGE_BASE_URL"].rstrip("/")
    ig = cfg["instagram"]
    dry = os.environ.get("DRY_RUN") == "1"
    token = os.environ.get("IG_ACCESS_TOKEN", "")
    user_id = "" if dry else (os.environ.get("IG_USER_ID")
                              or resolve_user_id(token, ig["graph_host"], ig["api_version"]))
    for name in files:
        url = f"{base}/{name}"
        if dry:
            print(f"[DRY_RUN] publicaria {url}")
            continue
        media_id = publish_story(url, user_id, token, ig["graph_host"], ig["api_version"])
        print(f"Story publicado: {name} -> media id {media_id}")


def cmd_refresh(cfg: dict) -> None:
    """Renova o token (vale 60 dias; o robô renova toda semana) e grava em out/new_token."""
    ig = cfg["instagram"]
    if "graph.instagram.com" not in ig["graph_host"]:
        print("Token de Página do Facebook não precisa de renovação.")
        return
    if not os.environ.get("IG_ACCESS_TOKEN"):
        print("::warning::Secret IG_ACCESS_TOKEN ainda não cadastrado; pulando a renovação.")
        return
    try:
        new, secs = refresh_token(os.environ["IG_ACCESS_TOKEN"], ig["graph_host"])
    except InstagramError as e:  # ex.: token com menos de 24h — tenta de novo na próxima semana
        print(f"::warning::Não foi possível renovar o token agora: {e}")
        return
    print(f"::add-mask::{new}")
    OUT.mkdir(exist_ok=True)
    (OUT / "new_token").write_text(new)
    print(f"Token renovado; válido por mais {secs // 86400} dias.")
    _gh_output("token_changed", "true" if new != os.environ["IG_ACCESS_TOKEN"] else "false")


def _gh_output(key: str, value: str) -> None:
    if path := os.environ.get("GITHUB_OUTPUT"):
        with open(path, "a") as f:
            f.write(f"{key}={value}\n")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "render"
    {"render": cmd_render, "publish": cmd_publish, "refresh": cmd_refresh}[cmd](load_cfg())
