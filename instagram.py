"""Publicação de stories pela API oficial do Instagram (Graph API)."""
from __future__ import annotations

import time

import requests


class InstagramError(RuntimeError):
    pass


def _call(method: str, url: str, **params) -> dict:
    r = requests.request(method, url, params=params, timeout=60)
    data = r.json() if r.content else {}
    if not r.ok or "error" in data:
        raise InstagramError(f"{r.status_code}: {data.get('error', data)}")
    return data


def resolve_user_id(token: str, host: str, version: str) -> str:
    """Descobre o ID da conta do Instagram a partir do próprio token."""
    return str(_call("GET", f"{host}/{version}/me", fields="user_id,username", access_token=token)["user_id"])


def refresh_token(token: str, host: str) -> tuple[str, int]:
    """Renova o token de longa duração do login do Instagram por mais 60 dias."""
    d = _call("GET", f"{host}/refresh_access_token", grant_type="ig_refresh_token", access_token=token)
    return d["access_token"], int(d.get("expires_in", 0))


def publish_story(image_url: str, ig_user_id: str, token: str, host: str, version: str) -> str:
    base = f"{host}/{version}"
    # 1) cria o container do story
    cont = _call("POST", f"{base}/{ig_user_id}/media",
                 media_type="STORIES", image_url=image_url, access_token=token)["id"]
    # 2) espera o processamento (a Meta recomenda checar a cada ~1 min, até 5 min)
    for _ in range(10):
        st = _call("GET", f"{base}/{cont}", fields="status_code", access_token=token).get("status_code")
        if st == "FINISHED":
            break
        if st in ("ERROR", "EXPIRED"):
            raise InstagramError(f"Container {cont} com status {st}")
        time.sleep(30)
    else:
        raise InstagramError(f"Container {cont} não ficou pronto a tempo")
    # 3) publica
    return _call("POST", f"{base}/{ig_user_id}/media_publish",
                 creation_id=cont, access_token=token)["id"]
