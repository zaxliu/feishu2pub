"""DocxXML -> WeChat Official Account article HTML.

Reuses the Zhihu converter and swaps the parts WeChat handles differently:
external links are stripped by WeChat (so the URL is printed as text),
formulas must be images, and styles must be inline (no <style>/class).
"""

from __future__ import annotations

import io
import re
from typing import Callable, Optional

from .convert import Converter, Resolver, esc, esc_attr, parse, walk

# Formula resolver: tex -> {"src", "width", "height"} (pixel size at RENDER_DPI) or None.
FormulaResolver = Callable[[str], Optional[dict]]
RENDER_DPI = 300

STYLES = {
    "h2": "font-size:20px;font-weight:bold;margin:32px 0 16px;",
    "h3": "font-size:17px;font-weight:bold;margin:24px 0 12px;",
    "p": "line-height:1.75;margin:0 0 16px;",
    "blockquote": "margin:0 0 16px;padding:12px 16px;background:#f6f7f9;border-left:4px solid #c8ccd2;color:#555;line-height:1.75;",
    "li": "line-height:1.75;",
    "code": "font-family:Menlo,Consolas,monospace;font-size:90%;background:#f3f4f6;padding:1px 4px;border-radius:3px;",
    "th": "border:1px solid #d0d4da;padding:6px 8px;background:#f3f4f6;font-weight:bold;",
    "td": "border:1px solid #d0d4da;padding:6px 8px;",
}
TABLE_OPEN = re.compile(r"<table [^>]*>")
PRE_OPEN = re.compile(r'<pre(?: lang="[^"]*")?>')


def formula_texts(xml: str) -> list[str]:
    seen: dict[str, None] = {}
    for n in walk(parse(xml)):
        if n.tag == "latex":
            seen.setdefault(norm_tex(_text(n)), None)
    return list(seen)


def _text(n) -> str:
    return "".join(c if isinstance(c, str) else _text(c) for c in n.children)


def norm_tex(tex: str) -> str:
    return " ".join(tex.split())


def render_formula(tex: str, fontsize: int = 15) -> bytes:
    """Render LaTeX to PNG with matplotlib mathtext (no network, no TeX install)."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    fig = plt.figure()
    fig.text(0, 0, f"${tex}$", fontsize=fontsize)
    buf = io.BytesIO()
    fig.savefig(buf, dpi=RENDER_DPI, format="png", bbox_inches="tight", pad_inches=0.04, transparent=False)
    plt.close(fig)
    return buf.getvalue()


class WechatConverter(Converter):
    def __init__(self, resolve: Resolver, formula: FormulaResolver):
        super().__init__(resolve)
        self.formula = formula

    def equation(self, tex: str, block: bool) -> str:
        tex = norm_tex(tex)
        info = self.formula(tex)
        if not info:
            self.warn("公式渲染或上传失败，已保留 LaTeX 源码")
            return f"<code>{esc(tex)}</code>"
        # Scale the 300 dpi render back to roughly body-text size on screen.
        w = round(info["width"] * 96 / RENDER_DPI)
        img = (f'<img src="{esc_attr(info["src"])}" alt="{esc_attr(tex)}"'
               f' style="width:{w}px;max-width:100%;vertical-align:middle;"/>')
        return f'<span style="display:block;text-align:center;">{img}</span>' if block else img

    def link(self, href: str, body: str) -> str:
        # WeChat strips <a> to anything but its own articles; keep the URL readable.
        self.warn("外链在公众号里不能点击，已在链接文字后附上网址")
        if esc(href) == body:
            return f'<span style="word-break:break-all;">{body}</span>'
        return f'{body}<br/><span style="color:#888;font-size:13px;word-break:break-all;">{esc(href)}</span>'

    def figure(self, info: dict, caption: str) -> str:
        img = f'<img src="{esc_attr(info["src"])}" style="max-width:100%;display:block;margin:0 auto;"/>'
        cap = (f'<span style="display:block;text-align:center;color:#888;font-size:13px;">{esc(caption)}</span>'
               if caption else "")
        return f'<p style="text-align:center;margin:0 0 16px;">{img}{cap}</p>'

    def convert(self, xml: str) -> str:
        return style(super().convert(xml))


def style(html: str) -> str:
    html = TABLE_OPEN.sub(
        '<table style="border-collapse:collapse;width:100%;font-size:14px;margin:0 0 16px;">', html)
    html = PRE_OPEN.sub(
        '<pre style="background:#f6f8fa;padding:12px;overflow-x:auto;font-size:13px;line-height:1.5;margin:0 0 16px;">',
        html)
    for tag, css in STYLES.items():
        html = html.replace(f"<{tag}>", f'<{tag} style="{css}">')
    return html
