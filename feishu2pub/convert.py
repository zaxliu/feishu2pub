"""Convert Feishu DocxXML (`lark-cli docs +fetch --doc-format xml`) to Zhihu article HTML.

The converter is pure: images are resolved through a callback, so it can run
offline in tests and in --dry-run mode. Anything Zhihu cannot represent is
downgraded and recorded in `Converter.warnings` for the manual review step.
"""

from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Callable, Iterator, Optional, Union
from urllib.parse import quote

VOID = {"img", "br", "hr", "col", "source"}
MEDIA = {"img", "whiteboard", "figure", "source"}
INLINE = {"b", "strong", "em", "i", "u", "del", "s", "code", "a", "span", "latex", "br", "cite"}
HEADING = re.compile(r"^h([1-9])$")
CODE_LANG = {"c++": "cpp", "shell": "bash", "golang": "go", "plaintext": "", "plain text": ""}


# ---- parse ---------------------------------------------------------------


@dataclass
class Node:
    tag: str
    attrs: dict
    children: list = field(default_factory=list)


Child = Union[Node, str]


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, {k: v or "" for k, v in attrs}))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse(xml: str) -> Node:
    b = _TreeBuilder()
    b.feed(xml)
    b.close()
    return b.root


def walk(node: Node) -> Iterator[Node]:
    for c in node.children:
        if isinstance(c, Node):
            yield c
            yield from walk(c)


def elements(node: Node, *tags: str) -> list[Node]:
    return [c for c in node.children if isinstance(c, Node) and (not tags or c.tag in tags)]


# ---- images ----------------------------------------------------------------


@dataclass(frozen=True)
class ImageRef:
    kind: str  # "whiteboard" | "media" (lark-cli +media-download --type)
    token: str


def image_ref(n: Node) -> Optional[ImageRef]:
    if n.tag == "whiteboard":
        tok = n.attrs.get("token") or n.attrs.get("src")
        return ImageRef("whiteboard", tok) if tok else None
    if n.tag == "img":
        tok = n.attrs.get("src") or n.attrs.get("token")
        return ImageRef("media", tok) if tok else None
    return None


def collect_images(xml: str) -> list[ImageRef]:
    """Image and whiteboard references in document order, deduplicated."""
    seen: dict[ImageRef, None] = {}
    for n in walk(parse(xml)):
        ref = image_ref(n)
        if ref:
            seen.setdefault(ref, None)
    return list(seen)


# Resolver returns {"src", "width", "height"} or None when the image is unavailable.
Resolver = Callable[[ImageRef], Optional[dict]]


# ---- helpers ---------------------------------------------------------------


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def esc_attr(s: str) -> str:
    return html.escape(s, quote=True)


def wrap(tag: str, inner: str) -> str:
    return f"<{tag}>{inner}</{tag}>" if inner.strip() else inner


def equation(tex: str, block: bool) -> str:
    tex = " ".join(tex.split())
    if block:
        tex += r"\\"  # Zhihu renders a formula ending in \\ as display math
    src = "https://www.zhihu.com/equation?tex=" + quote(tex, safe="")
    return f'<img src="{src}" alt="{esc_attr(tex)}" eeimg="1"/>'


def image_html(info: dict, caption: str = "") -> str:
    src = esc_attr(info["src"])
    cap = esc_attr(caption)
    figcaption = f"<figcaption>{esc(caption)}</figcaption>" if caption else ""
    return (
        f'<figure data-size="normal"><img src="{src}" data-caption="{cap}" data-size="normal"'
        f' data-rawwidth="{info.get("width", 0)}" data-rawheight="{info.get("height", 0)}"'
        f' data-original-src="{src}" data-watermark="original" data-watermark-src=""'
        f' data-private-watermark-src=""/>{figcaption}</figure>'
    )


def is_blank(c: Child) -> bool:
    return isinstance(c, str) and not c.strip()


# ---- converter -------------------------------------------------------------


class Converter:
    def __init__(self, resolve: Resolver):
        self.resolve = resolve
        self.title = ""
        self.warnings: Counter = Counter()
        self._h_base = 1

    def warn(self, msg: str) -> None:
        self.warnings[msg] += 1

    # -- output hooks (overridden by other targets, e.g. WeChat)

    def equation(self, tex: str, block: bool) -> str:
        return equation(tex, block)

    def link(self, href: str, body: str) -> str:
        return f'<a href="{esc_attr(href)}">{body}</a>'

    def figure(self, info: dict, caption: str) -> str:
        return image_html(info, caption)

    def convert(self, xml: str) -> str:
        root = parse(xml)
        levels = [int(HEADING.match(n.tag).group(1)) for n in walk(root) if HEADING.match(n.tag)]
        self._h_base = min(levels) if levels else 1
        return self.blocks(root.children)

    # -- block level

    def blocks(self, children: list) -> str:
        out: list[str] = []
        run: list = []

        def flush():
            s = self.inline(run).strip()
            if s:
                out.append(f"<p>{s}</p>")
            run.clear()

        for c in children:
            if isinstance(c, str):
                if c.strip():
                    run.append(c)
            elif c.tag in INLINE:
                run.append(c)
            else:
                flush()
                out.append(self.block(c))
        flush()
        return "".join(out)

    def block(self, n: Node) -> str:
        t = n.tag
        if t == "title":
            self.title = self.text(n).strip()
            return ""
        if t == "p":
            return self.paragraph(n)
        if HEADING.match(t):
            return self.heading(n)
        if t in ("ul", "ol"):
            return self.list(n)
        if t == "checkbox":
            mark = "☑" if n.attrs.get("done") == "true" else "☐"
            return f"<p>{mark} {self.inline(n.children).strip()}</p>"
        if t == "blockquote":
            return self.quote(n.children)
        if t == "callout":
            self.warn("高亮块（callout）降级为引用，背景色丢失")
            return self.quote(n.children, prefix=n.attrs.get("emoji", ""))
        if t == "pre":
            return self.code_block(n)
        if t == "hr":
            return "<hr/>"
        if t == "table":
            return self.table(n)
        if t in ("img", "whiteboard"):
            return self.image(n)
        if t == "figure":
            return self.blocks(n.children)
        if t == "source":
            self.warn("附件无法上传到知乎，已替换为文字占位")
            return f"<p>[附件：{esc(n.attrs.get('name', ''))}]</p>"
        if t == "grid":
            self.warn("分栏（grid）已展开为上下顺序排列")
            return self.blocks(n.children)
        if t == "column":
            return self.blocks(n.children)
        if n.children:
            self.warn(f"未识别的块 <{t}>，已展开其内容")
            return self.blocks(n.children)
        self.warn(f"不支持的飞书块 <{t}>，已替换为占位文字")
        return f"<p>[飞书 {esc(t)} 块未导出]</p>"

    def paragraph(self, n: Node) -> str:
        meaningful = [c for c in n.children if not is_blank(c)]
        if len(meaningful) == 1 and isinstance(meaningful[0], Node) and meaningful[0].tag == "latex":
            return f"<p>{self.equation(self.text(meaningful[0]), block=True)}</p>"
        # Images may sit inside a paragraph; Zhihu needs them as separate figures.
        out: list[str] = []
        run: list = []

        def flush():
            s = self.inline(run).strip()
            if s:
                out.append(f"<p>{s}</p>")
            run.clear()

        for c in n.children:
            if isinstance(c, Node) and c.tag in MEDIA:
                flush()
                out.append(self.block(c))
            else:
                run.append(c)
        flush()
        return "".join(out)

    def heading(self, n: Node) -> str:
        level = int(n.tag[1]) - self._h_base + 1
        body = self.inline(n.children).strip()
        marker = n.attrs.get("seq-marker", "").strip()
        if marker:
            body = f"{esc(marker)} {body}"
        if level == 1:
            return f"<h2>{body}</h2>"
        if level == 2:
            return f"<h3>{body}</h3>"
        self.warn("三级及以下标题降级为加粗段落（知乎只有两级标题）")
        return f"<p><b>{body}</b></p>"

    def list(self, n: Node) -> str:
        items = []
        for li in elements(n):
            nested = "".join(self.list(c) for c in elements(li, "ul", "ol"))
            body = [c for c in li.children if not (isinstance(c, Node) and c.tag in ("ul", "ol"))]
            items.append(f"<li>{self.inline(body).strip()}{nested}</li>")
        return f"<{n.tag}>{''.join(items)}</{n.tag}>" if items else ""

    def quote(self, children: list, prefix: str = "") -> str:
        lines: list[str] = []
        for c in children:
            if isinstance(c, str):
                if c.strip():
                    lines.append(esc(c.strip()))
            elif c.tag in ("ul", "ol"):
                lines.extend(self.flat_list(c))
            elif c.tag == "checkbox":
                mark = "☑" if c.attrs.get("done") == "true" else "☐"
                lines.append(f"{mark} {self.inline(c.children).strip()}")
            else:
                s = self.inline(c.children if c.tag == "p" else [c]).strip()
                if s:
                    lines.append(s)
        if not lines:
            return ""
        if prefix:
            lines[0] = f"{esc(prefix)} {lines[0]}"
        return f"<blockquote>{'<br/>'.join(lines)}</blockquote>"

    def flat_list(self, n: Node, depth: int = 0) -> list[str]:
        """List items as text lines, for containers that cannot hold <ul>."""
        lines = []
        for i, li in enumerate(elements(n, "li"), 1):
            mark = f"{i}." if n.tag == "ol" else "•"
            body = [c for c in li.children if not (isinstance(c, Node) and c.tag in ("ul", "ol"))]
            lines.append(f"{'　' * depth}{mark} {self.inline(body).strip()}")
            for sub in elements(li, "ul", "ol"):
                lines.extend(self.flat_list(sub, depth + 1))
        return lines

    def code_block(self, n: Node) -> str:
        lang = n.attrs.get("lang", "").strip().lower()
        lang = CODE_LANG.get(lang, lang)
        code = self.text(n).strip("\n")
        attr = f' lang="{esc_attr(lang)}"' if lang else ""
        if n.attrs.get("caption"):
            self.warn("代码块标题（caption）丢失")
        return f"<pre{attr}>{esc(code)}</pre>"

    def table(self, n: Node) -> str:
        trs = [x for x in walk(n) if x.tag == "tr"]
        header_rows = {id(tr) for thead in walk(n) if thead.tag == "thead" for tr in walk(thead) if tr.tag == "tr"}
        occupied: set = set()
        merged = False
        rows = []
        for r, tr in enumerate(trs):
            cells: list[str] = []
            c = 0
            cell_tag = "th" if id(tr) in header_rows else "td"

            def pad():
                nonlocal c
                while (r, c) in occupied:
                    cells.append(f"<{cell_tag}></{cell_tag}>")
                    c += 1

            for cell in elements(tr, "th", "td"):
                pad()
                tag = "th" if cell.tag == "th" or id(tr) in header_rows else "td"
                cells.append(f"<{tag}>{self.cell(cell)}</{tag}>")
                cs = max(int(cell.attrs.get("colspan") or 1), 1)
                rs = max(int(cell.attrs.get("rowspan") or 1), 1)
                if cs > 1 or rs > 1:
                    merged = True
                for dr in range(rs):
                    for dc in range(cs):
                        if dr or dc:
                            occupied.add((r + dr, c + dc))
                c += 1
            pad()
            rows.append(f"<tr>{''.join(cells)}</tr>")
        if merged:
            self.warn("表格合并单元格已拆开（知乎表格不支持合并）")
        return (
            '<table data-draft-node="block" data-draft-type="table" data-size="normal"'
            f' data-row-style="normal"><tbody>{"".join(rows)}</tbody></table>'
        )

    def cell(self, cell: Node) -> str:
        parts: list[str] = []
        for c in cell.children:
            if isinstance(c, str):
                if c.strip():
                    parts.append(esc(c.strip()))
            elif c.tag in ("ul", "ol"):
                parts.extend(self.flat_list(c))
            else:
                s = self.inline(c.children if c.tag == "p" else [c]).strip()
                if s:
                    parts.append(s)
        return "<br/>".join(parts)

    def image(self, n: Node) -> str:
        ref = image_ref(n)
        info = self.resolve(ref) if ref else None
        if not info:
            self.warn("有图片下载或上传失败，已用占位文字代替")
            return f"<p>[图片缺失：{esc(ref.token if ref else n.tag)}]</p>"
        return self.figure(info, n.attrs.get("caption", ""))

    # -- inline level

    def inline(self, children: list) -> str:
        out: list[str] = []
        for c in children:
            if isinstance(c, str):
                out.append(esc(c))
                continue
            t = c.tag
            if t in ("b", "strong"):
                out.append(wrap("b", self.inline(c.children)))
            elif t in ("em", "i"):
                out.append(wrap("i", self.inline(c.children)))
            elif t in ("del", "s"):
                out.append(wrap("del", self.inline(c.children)))
            elif t in ("u", "span"):  # Zhihu has no underline; colours/comment anchors dropped
                out.append(self.inline(c.children))
            elif t == "code":
                out.append(f"<code>{esc(self.text(c))}</code>")
            elif t == "a":
                href = c.attrs.get("href", "")
                body = self.inline(c.children) or esc(href)
                out.append(self.link(href, body) if href else body)
            elif t == "latex":
                out.append(self.equation(self.text(c), block=False))
            elif t == "br":
                out.append("<br/>")
            elif t == "cite":
                out.append(self.cite(c))
            elif t == "p":
                out.append(("<br/>" if out else "") + self.inline(c.children))
            elif t in MEDIA:
                self.warn("列表/表格/引用内的图片无法内嵌，已替换为文字占位")
                out.append("[图片]")
            else:
                self.warn(f"未识别的行内标签 <{t}>，已保留文字")
                out.append(self.inline(c.children))
        return "".join(out)

    def cite(self, c: Node) -> str:
        kind = c.attrs.get("type", "")
        if kind == "citation":
            return "、".join(self.inline([a]) for a in elements(c, "a"))
        text = self.text(c).strip()
        if kind == "user":
            self.warn("@人 已转为纯文本")
            return esc(text if text.startswith("@") else f"@{text or '用户'}")
        self.warn("飞书文档引用已转为纯文本")
        return esc(text or "[飞书文档]")

    def text(self, n: Node) -> str:
        parts = []
        for c in n.children:
            if isinstance(c, str):
                parts.append(c)
            elif c.tag == "br":
                parts.append("\n")
            else:
                parts.append(self.text(c))
        return "".join(parts)
