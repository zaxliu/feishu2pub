"""Feishu access through lark-cli (auth and profiles are handled by the CLI)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


class FeishuError(RuntimeError):
    pass


def _profile_args() -> list[str]:
    profile = os.environ.get("LARK_PROFILE", "").strip()
    return ["--profile", profile] if profile else []


def run_lark(args: list[str], timeout: float = 120) -> dict:
    """Run lark-cli and return its `data` payload, raising on `ok: false`."""
    cmd = ["lark-cli", *args, *_profile_args()]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise FeishuError("lark-cli not found; install @larksuite/cli") from e
    for stream in (p.stdout, p.stderr):
        stream = stream.strip()
        if not stream:
            continue
        try:
            payload = json.loads(stream)
        except json.JSONDecodeError:
            continue
        if payload.get("ok"):
            return payload.get("data", {})
        err = payload.get("error", {})
        raise FeishuError(f"{err.get('code', '')} {err.get('message', stream[:300])}".strip())
    raise FeishuError(f"lark-cli exited {p.returncode}: {(p.stderr or p.stdout)[:300]}")


def fetch_doc(url_or_token: str) -> dict:
    """Return {document_id, revision_id, xml} for a docx or wiki URL."""
    data = run_lark(["docs", "+fetch", "--doc", url_or_token, "--doc-format", "xml"])
    doc = data["document"]
    return {
        "document_id": doc["document_id"],
        "revision_id": doc.get("revision_id"),
        "xml": doc["content"],
    }


def download_media(token: str, kind: str, dest_base: Path) -> Path:
    """Download an image (kind='media') or whiteboard snapshot (kind='whiteboard').

    lark-cli appends the file extension itself, so pass a path without one.
    """
    dest_base.parent.mkdir(parents=True, exist_ok=True)
    data = run_lark([
        "docs", "+media-download", "--token", token, "--type", kind,
        "--output", str(dest_base), "--overwrite",
    ])
    return Path(data["saved_path"])
