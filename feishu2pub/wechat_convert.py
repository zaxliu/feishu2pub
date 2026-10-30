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


# mathtext has no \text; route it to the sans slot, which render_formula points at a CJK font.
TEXT_CMD = re.compile(r"\\text\{([^{}]*)\}")
CJK_FONTS = ("PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", "Source Han Sans SC",
             "Microsoft YaHei", "Arial Unicode MS")


# LaTeX aliases mathtext doesn't know.
ALIASES = re.compile(r"\\(le|ge)(?![A-Za-z])")
# \underbrace{x}_{label} -> \underset{label}{x}; label may hold one level of braces (\text{...}).
UNDERBRACE = re.compile(r"\\underbrace\{([^{}]*)\}_\{((?:[^{}]|\{[^{}]*\})*)\}")


BMOD = re.compile(r"\\bmod(?![A-Za-z])")


def mathtext_source(tex: str) -> str:
    tex = BMOD.sub(r"\\ \\mathrm{mod}\\ ", tex)
    tex = ALIASES.sub(lambda m: "\\" + m.group(1) + "q", tex)
    tex = UNDERBRACE.sub(lambda m: r"\underset{" + m.group(2) + "}{" + m.group(1) + "}", tex)
    return TEXT_CMD.sub(lambda m: r"\mathsf{" + m.group(1).replace(" ", r"\ ") + "}", tex)


def _cjk_font() -> Optional[str]:
    from matplotlib import font_manager

    names = {f.name for f in font_manager.fontManager.ttflist}
    return next((n for n in CJK_FONTS if n in names), None)


def render_formula(tex: str, fontsize: int = 15) -> bytes:
    """Render LaTeX to PNG with matplotlib mathtext (no network, no TeX install)."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    rc = {"mathtext.fontset": "custom", "mathtext.rm": "STIXGeneral", "mathtext.it": "STIXGeneral:italic",
          "mathtext.bf": "STIXGeneral:bold", "mathtext.fallback": "stix"}
    if font := _cjk_font():
        rc["mathtext.sf"] = font
    with matplotlib.rc_context(rc):
        fig = plt.figure()
        fig.text(0, 0, f"${mathtext_source(tex)}$", fontsize=fontsize)
        buf = io.BytesIO()
        fig.savefig(buf, dpi=RENDER_DPI, format="png", bbox_inches="tight", pad_inches=0.04, transparent=False)
        plt.close(fig)
    return buf.getvalue()


class WechatConverter(Converter):
    def __init__(self, resolve: Resolver, formula: FormulaResolver, link_urls: bool = True):
        super().__init__(resolve)
        self.formula = formula
        self.link_urls = link_urls

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
        if esc(href) == body:
            return f'<span style="word-break:break-all;">{body}</span>'
        if not self.link_urls:
            self.warn("外链在公众号里不能点击，为控制字数只保留了链接文字")
            return body
        self.warn("外链在公众号里不能点击，已在链接文字后附上网址")
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


def cut_at_heading(html: str, needle: str, note: str) -> tuple[str, int]:
    """Drop everything from the first <h2> whose text contains `needle`; append `note` as a paragraph.

    Returns (html, number of headings dropped). Used to fit WeChat's 20000-character limit
    by leaving appendices to the full article behind 阅读原文.
    """
    heads = list(re.finditer(r"<h2[^>]*>(.*?)</h2>", html, re.S))
    start = next((m.start() for m in heads if needle in re.sub(r"<[^>]+>", "", m.group(1))), None)
    if start is None:
        return html, 0
    dropped = sum(1 for m in heads if m.start() >= start)
    return html[:start] + f'<p style="{STYLES["p"]}color:#888;">{esc(note)}</p>', dropped
