"""Import a Feishu doc into a WeChat Official Account draft (never publishes).

    python -m feishu2pub wechat <feishu docx/wiki URL> [--dry-run] [--new]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from PIL import Image

from . import feishu
from .state import OUT, ROOT, load_state, save_state
from .convert import ImageRef, collect_images
from .images import Prepared, prepare, shrink
from .wechat import Wechat, WechatError
from .wechat_convert import WechatConverter, formula_texts, render_formula
from .zhihu import load_env


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="feishu2pub wechat", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("doc", help="Feishu docx or wiki URL / token")
    ap.add_argument("--dry-run", action="store_true", help="convert locally, skip all WeChat calls")
    ap.add_argument("--new", action="store_true", help="create a new draft even if one is mapped")
    ap.add_argument("--author", default="", help="author shown on the article")
    args = ap.parse_args(argv)

    load_env(ROOT / ".env")
    state = load_state()
    wx_state = state.setdefault("wechat", {"docs": {}, "images": {}, "formulas": {}})

    print("fetching Feishu doc ...")
    doc = feishu.fetch_doc(args.doc)
    doc_id = doc["document_id"]
    work = OUT / doc_id
    media_dir = work / "media"
    refs = collect_images(doc["xml"])
    texs = formula_texts(doc["xml"])
    print(f"  document {doc_id} rev {doc['revision_id']}, {len(refs)} images/whiteboards, {len(texs)} formulas")

    wx = None if args.dry_run else Wechat.from_env()
    prepared: dict[ImageRef, Prepared] = {}

    def upload(p: Prepared) -> tuple[str, str]:
        md5 = hashlib.md5(p.data).hexdigest()
        if md5 in wx_state["images"]:
            return wx_state["images"][md5], "cached"
        url = wx.upload_inline_image(p.data, p.mime, p.ext)
        wx_state["images"][md5] = url
        return url, "uploaded"

    def process(ref: ImageRef):
        try:
            path = feishu.download_media(ref.token, ref.kind, media_dir / ref.token)
            p = shrink(prepare(path, trim=ref.kind == "whiteboard"))
            prepared[ref] = p
            info = {"width": p.width, "height": p.height}
            if not wx:
                return ref, {**info, "src": path.resolve().as_uri()}, f"local {len(p.data) // 1024}KB"
            url, how = upload(p)
            return ref, {**info, "src": url}, f"{how} {p.ext} {len(p.data) // 1024}KB"
        except (feishu.FeishuError, WechatError, OSError, ValueError) as e:
            return ref, None, f"FAILED: {e}"

    print("downloading and uploading images ...")
    resolved: dict[ImageRef, Optional[dict]] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for ref, info, how in pool.map(process, refs):
            resolved[ref] = info
            size = f"{info['width']}x{info['height']}" if info else ""
            print(f"  {ref.kind:10} {ref.token}  {size:>10}  {how}")

    formulas: dict[str, Optional[dict]] = {}
    for i, tex in enumerate(texs):
        try:
            png = render_formula(tex)
            with Image.open(io.BytesIO(png)) as im:
                w, h = im.size
            (work / f"formula_{i}.png").write_bytes(png)
            if not wx:
                formulas[tex] = {"src": (work / f"formula_{i}.png").resolve().as_uri(), "width": w, "height": h}
                continue
            url, how = upload(Prepared(png, "image/png", "png", w, h))
            formulas[tex] = {"src": url, "width": w, "height": h}
            print(f"  formula {i}  {w}x{h}  {how}")
        except (WechatError, ValueError, RuntimeError) as e:
            formulas[tex] = None
            print(f"  formula {i} FAILED: {e}")

    conv = WechatConverter(lambda ref: resolved.get(ref), lambda tex: formulas.get(tex))
    body = conv.convert(doc["xml"])
    title = conv.title or "未命名"
    work.mkdir(parents=True, exist_ok=True)
    (work / "wechat.html").write_text(
        f'<!doctype html><meta charset="utf-8"><title>{title}</title>'
        f'<body style="max-width:680px;margin:auto;font-size:16px;"><h1>{title}</h1>\n{body}\n</body>')
    print(f"converted: {len(body)} chars -> {work / 'wechat.html'}")
    # Verified: WeChat accepted 27k chars of HTML with 13k visible; the limit counts text, not markup.
    text_len = len(re.sub(r"<[^>]+>", "", body))
    if text_len >= 20000:
        print(f"  warning: {text_len} visible characters, over WeChat's 20000 limit")

    if conv.warnings:
        print("needs review (format downgrades):")
        for msg, n in conv.warnings.most_common():
            print(f"  - {msg} ×{n}")

    if not wx:
        print("dry run: no WeChat draft written")
        return 0

    mapped = wx_state["docs"].get(doc_id, {})
    cover = mapped.get("thumb_media_id")
    if not cover:
        first = next((prepared[r] for r in refs if r in prepared), None)
        if not first:
            raise WechatError("no image available for the cover (thumb_media_id is required)")
        cover = wx.add_cover(first.data, first.mime, first.ext)
        print("  cover uploaded from the first image")

    article = {
        "article_type": "news",
        "title": title,
        "author": args.author,
        "content": body,
        "thumb_media_id": cover,
        "need_open_comment": 1,
        "only_fans_can_comment": 0,
    }
    media_id = None if args.new else mapped.get("media_id")
    if media_id:
        try:
            wx.update_draft(media_id, article)
        except WechatError as e:
            print(f"  mapped draft not writable ({e}); creating a new one")
            media_id = None
    if not media_id:
        media_id = wx.add_draft(article)

    wx_state["docs"][doc_id] = {"media_id": media_id, "thumb_media_id": cover, "title": title,
                                "revision_id": doc["revision_id"]}
    save_state(state)
    print(f"draft saved (not published): media_id {media_id}")
    print("open 公众号后台 → 内容管理 → 草稿箱 to review and publish")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (feishu.FeishuError, WechatError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
