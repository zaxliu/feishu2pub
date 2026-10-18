"""Import a Feishu doc into a Zhihu article draft (never publishes).

    python -m feishu2pub zhihu <feishu docx/wiki URL> [--dry-run] [--new]
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from . import feishu
from .convert import Converter, ImageRef, collect_images
from .images import prepare
from .state import OUT, ROOT, load_state, save_state
from .zhihu import Zhihu, ZhihuError, load_env

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="feishu2pub zhihu", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("doc", help="Feishu docx or wiki URL / token")
    ap.add_argument("--dry-run", action="store_true", help="convert locally, skip all Zhihu calls")
    ap.add_argument("--new", action="store_true", help="create a new draft even if one is mapped")
    ap.add_argument("--no-trim", action="store_true", help="keep whiteboard margins")
    args = ap.parse_args(argv)

    load_env(ROOT / ".env")
    state = load_state()

    print("fetching Feishu doc ...")
    doc = feishu.fetch_doc(args.doc)
    doc_id = doc["document_id"]
    work = OUT / doc_id
    media_dir = work / "media"
    refs = collect_images(doc["xml"])
    print(f"  document {doc_id} rev {doc['revision_id']}, {len(refs)} images/whiteboards")

    zh = None if args.dry_run else Zhihu.from_env()
    if zh:
        print(f"  Zhihu account: {zh.me().get('name')}")

    def process(ref: ImageRef) -> tuple[ImageRef, Optional[dict], str]:
        try:
            path = feishu.download_media(ref.token, ref.kind, media_dir / ref.token)
            img = prepare(path, trim=ref.kind == "whiteboard" and not args.no_trim)
            info = {"width": img.width, "height": img.height}
            if not zh:
                return ref, {**info, "src": path.resolve().as_uri()}, "local"
            md5 = hashlib.md5(img.data).hexdigest()
            cached = state["images"].get(md5)
            if cached:
                return ref, {**info, "src": cached}, "cached"
            up = zh.upload_image(img.data, img.mime, img.ext)
            state["images"][md5] = up["src"]
            return ref, {**info, "src": up["src"]}, "uploaded"
        except (feishu.FeishuError, ZhihuError, OSError) as e:
            return ref, None, f"FAILED: {e}"

    print("downloading and uploading images ...")
    resolved: dict[ImageRef, Optional[dict]] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for ref, info, how in pool.map(process, refs):
            resolved[ref] = info
            size = f"{info['width']}x{info['height']}" if info else ""
            print(f"  {ref.kind:10} {ref.token}  {size:>10}  {how}")

    conv = Converter(lambda ref: resolved.get(ref))
    body = conv.convert(doc["xml"])
    title = conv.title or "未命名"
    work.mkdir(parents=True, exist_ok=True)
    (work / "article.html").write_text(
        f'<!doctype html><meta charset="utf-8"><title>{title}</title><h1>{title}</h1>\n{body}\n'
    )
    print(f"converted: {len(body)} chars -> {work / 'article.html'}")

    if conv.warnings:
        print("needs review (format downgrades):")
        for msg, n in conv.warnings.most_common():
            print(f"  - {msg} ×{n}")

    if not zh:
        print("dry run: no Zhihu draft written")
        return 0

    mapped = state["docs"].get(doc_id, {}).get("article_id")
    article_id = None if args.new else mapped
    if article_id:
        try:
            zh.patch_draft(article_id, title=title, content=body)
        except ZhihuError as e:
            print(f"  mapped draft {article_id} not writable ({e}); creating a new one")
            article_id = None
    if not article_id:
        article_id = zh.create_draft(title)
        zh.patch_draft(article_id, title=title, content=body)

    state["docs"][doc_id] = {"article_id": article_id, "title": title, "revision_id": doc["revision_id"]}
    save_state(state)
    print(f"draft saved (not published): https://zhuanlan.zhihu.com/p/{article_id}/edit")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (feishu.FeishuError, ZhihuError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
