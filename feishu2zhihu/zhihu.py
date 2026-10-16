"""Minimal Zhihu web client: drafts and image upload, cookie auth only.

Endpoints adapted from zhihu_obsidian (publish_service.ts, image_service.ts)
and KrisTHL181/zhihu-cli (upload_image.py, MIT).
"""

from __future__ import annotations

import base64
import email.utils
import hashlib
import hmac
import os
import time
from pathlib import Path

import httpx

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
OSS_UPLOAD = "https://zhihu-pics-upload.zhimg.com"


class ZhihuError(RuntimeError):
    pass


def load_env(path: str | Path = ".env") -> None:
    """Load KEY=VALUE lines into os.environ without overriding existing vars."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Zhihu:
    def __init__(self, z_c0: str, xsrf: str, d_c0: str, timeout: float = 20):
        if not (z_c0 and xsrf and d_c0):
            raise ZhihuError("missing ZHIHU_Z_C0 / ZHIHU_XSRF / ZHIHU_D_C0")
        self.xsrf = xsrf
        self.http = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"},
            cookies={"z_c0": z_c0, "_xsrf": xsrf, "d_c0": d_c0},
        )

    @classmethod
    def from_env(cls) -> "Zhihu":
        return cls(
            os.environ.get("ZHIHU_Z_C0", ""),
            os.environ.get("ZHIHU_XSRF", ""),
            os.environ.get("ZHIHU_D_C0", ""),
        )

    def _check(self, r: httpx.Response, what: str) -> httpx.Response:
        if r.status_code >= 400:
            raise ZhihuError(f"{what} failed: HTTP {r.status_code} {r.text[:300]}")
        return r

    def _write_headers(self, referer: str) -> dict:
        return {
            "x-xsrftoken": self.xsrf,
            "x-requested-with": "fetch",
            "origin": "https://zhuanlan.zhihu.com",
            "referer": referer,
        }

    # ---- account -------------------------------------------------------

    def me(self) -> dict:
        r = self.http.get("https://www.zhihu.com/api/v4/me")
        return self._check(r, "get me").json()

    # ---- drafts --------------------------------------------------------

    def create_draft(self, title: str) -> str:
        r = self.http.post(
            "https://zhuanlan.zhihu.com/api/articles/drafts",
            json={"title": title, "delta_time": 0, "can_reward": False},
            headers=self._write_headers("https://zhuanlan.zhihu.com/write"),
        )
        return str(self._check(r, "create draft").json()["id"])

    def patch_draft(self, article_id: str, **fields) -> None:
        fields.setdefault("delta_time", 30)
        r = self.http.patch(
            f"https://zhuanlan.zhihu.com/api/articles/{article_id}/draft",
            json=fields,
            headers=self._write_headers(f"https://zhuanlan.zhihu.com/p/{article_id}/edit"),
        )
        self._check(r, "patch draft")

    def get_draft(self, article_id: str) -> dict:
        r = self.http.get(f"https://zhuanlan.zhihu.com/api/articles/{article_id}/draft")
        return self._check(r, "get draft").json()

    # ---- images --------------------------------------------------------

    def upload_image(self, data: bytes, mime: str = "image/jpeg", ext: str = "jpg") -> dict:
        """Upload image bytes; returns {src, original_src}."""
        md5 = hashlib.md5(data).hexdigest()
        r = self.http.post(
            "https://api.zhihu.com/images",
            json={"image_hash": md5, "source": "article"},
        )
        reg = self._check(r, "register image").json()
        up = reg["upload_file"]
        image_id, state = up["image_id"], up["state"]
        if state == 2:  # not on server yet
            self._put_oss(up["object_key"], data, reg["upload_token"], mime)
        elif state != 1:  # 1 = already uploaded (same hash)
            raise ZhihuError(f"unexpected image state {state}")
        return self._poll_image(str(image_id), md5, ext)

    def _put_oss(self, obj_key: str, data: bytes, token: dict, mime: str) -> None:
        date = email.utils.formatdate(usegmt=True)
        sts = token["access_token"]
        to_sign = f"PUT\n\n{mime}\n{date}\nx-oss-security-token:{sts}\n/zhihu-pics/{obj_key}"
        sig = base64.b64encode(
            hmac.new(token["access_key"].encode(), to_sign.encode(), hashlib.sha1).digest()
        ).decode()
        r = httpx.put(
            f"{OSS_UPLOAD}/{obj_key}",
            content=data,
            headers={
                "Content-Type": mime,
                "Date": date,
                "x-oss-security-token": sts,
                "Authorization": f"OSS {token['access_id']}:{sig}",
            },
            timeout=60,
        )
        self._check(r, "OSS upload")

    def _poll_image(self, image_id: str, md5: str, ext: str, tries: int = 2) -> dict:
        # Images on unpublished drafts stay "processing", so don't wait long:
        # Zhihu rewrites the hash-based URL below to its private CDN on save.
        for i in range(tries):
            r = self.http.get(f"https://api.zhihu.com/images/{image_id}")
            d = self._check(r, "poll image").json()
            if d.get("status") == "success":
                return {"src": d["src"], "original_src": d.get("original_src", d["src"])}
            if i + 1 < tries:
                time.sleep(1)
        src = f"https://picx.zhimg.com/v2-{md5}.{ext}"
        return {"src": src, "original_src": src, "fallback": True}
