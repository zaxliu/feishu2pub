"""Minimal WeChat Official Account client: official API, drafts only (never publishes).

Verified on a personal-entity account: stable_token, material/add_material,
media/uploadimg, draft/add, draft/get. The caller's public IP must be on the
API IP whitelist (errcode 40164 otherwise).
"""

from __future__ import annotations

import json
import os
import time

import httpx

API = "https://api.weixin.qq.com/cgi-bin"


class WechatError(RuntimeError):
    pass


class Wechat:
    def __init__(self, appid: str, secret: str):
        self.appid, self.secret = appid, secret
        self.c = httpx.Client(timeout=60, trust_env=False)
        self._token, self._expires = "", 0.0

    @classmethod
    def from_env(cls) -> "Wechat":
        appid, secret = os.environ.get("WECHAT_APPID", ""), os.environ.get("WECHAT_APPSECRET", "")
        if not appid or not secret:
            raise WechatError("WECHAT_APPID / WECHAT_APPSECRET missing in .env")
        return cls(appid, secret)

    @staticmethod
    def _check(r: httpx.Response, step: str) -> dict:
        try:
            data = r.json()
        except ValueError as e:
            raise WechatError(f"{step}: HTTP {r.status_code} non-JSON response") from e
        if data.get("errcode"):
            raise WechatError(f"{step}: errcode={data['errcode']} {data.get('errmsg', '')}")
        return data

    def token(self) -> str:
        if time.time() < self._expires - 300:
            return self._token
        data = self._check(self.c.post(f"{API}/stable_token", json={
            "grant_type": "client_credential", "appid": self.appid, "secret": self.secret}), "stable_token")
        self._token, self._expires = data["access_token"], time.time() + data.get("expires_in", 7200)
        return self._token

    def _post_json(self, path: str, body: dict) -> dict:
        # ensure_ascii=False: WeChat stores \uXXXX escapes literally otherwise.
        r = self.c.post(f"{API}/{path}", params={"access_token": self.token()},
                        content=json.dumps(body, ensure_ascii=False).encode(),
                        headers={"Content-Type": "application/json; charset=utf-8"})
        return self._check(r, path)

    def upload_inline_image(self, data: bytes, mime: str, ext: str) -> str:
        """Body image (jpg/png < 1MB); returns an mmbiz.qpic.cn URL. Not counted against material quota."""
        r = self.c.post(f"{API}/media/uploadimg", params={"access_token": self.token()},
                        files={"media": (f"image.{ext}", data, mime)})
        return self._check(r, "uploadimg")["url"]

    def add_cover(self, data: bytes, mime: str, ext: str) -> str:
        """Permanent image material for thumb_media_id."""
        r = self.c.post(f"{API}/material/add_material", params={"access_token": self.token(), "type": "image"},
                        files={"media": (f"cover.{ext}", data, mime)})
        return self._check(r, "add_material")["media_id"]

    def add_draft(self, article: dict) -> str:
        return self._post_json("draft/add", {"articles": [article]})["media_id"]

    def update_draft(self, media_id: str, article: dict) -> None:
        self._post_json("draft/update", {"media_id": media_id, "index": 0, "articles": article})

    def get_draft(self, media_id: str) -> dict:
        return self._post_json("draft/get", {"media_id": media_id})["news_item"][0]
