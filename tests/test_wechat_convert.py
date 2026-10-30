import io

from PIL import Image

from feishu2pub.convert import ImageRef
from feishu2pub.images import Prepared, shrink
from feishu2pub.wechat_convert import WechatConverter, formula_texts

IMG = {"src": "https://mmbiz.qpic.cn/x/0", "width": 800, "height": 400}
F = {"src": "https://mmbiz.qpic.cn/f/0", "width": 600, "height": 90}


def conv(xml, images=None, formulas=None):
    c = WechatConverter(lambda r: (images or {}).get(r), lambda t: (formulas or {}).get(t))
    return c, c.convert(xml)


def test_link_keeps_url_as_text():
    c, out = conv('<p><a href="https://a.com/x">文档</a></p>')
    assert "<a " not in out
    assert "文档<br/>" in out and "https://a.com/x</span>" in out
    assert c.warnings


def test_bare_link_not_duplicated():
    _, out = conv('<p><a href="https://a.com">https://a.com</a></p>')
    assert out.count("https://a.com") == 1


def test_block_formula_image_centered():
    _, out = conv('<p><latex>a  +  b</latex></p>', formulas={"a + b": F})
    assert 'src="https://mmbiz.qpic.cn/f/0"' in out and "text-align:center" in out
    assert "width:192px" in out  # 600 px at 300 dpi -> 192 css px


def test_missing_formula_falls_back_to_code():
    c, out = conv('<p>x <latex>y^2</latex></p>')
    assert "<code" in out and "y^2" in out and c.warnings


def test_inline_styles_and_table():
    _, out = conv('<h1>A</h1><p>t</p><table><tbody><tr><td><p>1</p></td></tr></tbody></table>')
    assert out.startswith('<h2 style="') and '<p style="' in out
    assert '<table style="border-collapse:collapse' in out and "data-draft" not in out
    assert '<td style="' in out


def test_figure_is_plain_img():
    _, out = conv('<whiteboard token="W"></whiteboard>', {ImageRef("whiteboard", "W"): IMG})
    assert "<figure" not in out and 'src="https://mmbiz.qpic.cn/x/0"' in out


def test_formula_texts_normalized_dedup():
    assert formula_texts("<p><latex>a  b</latex><latex>a b</latex></p>") == ["a b"]


def test_shrink_large_png_under_limit():
    im = Image.effect_noise((1400, 1400), 80).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    p = shrink(Prepared(buf.getvalue(), "image/png", "png", *im.size))
    assert len(p.data) < 1_000_000 and p.ext in ("png", "jpg")


def test_link_url_dropped_when_disabled():
    c = WechatConverter(lambda r: None, lambda t: None, link_urls=False)
    out = c.convert('<p><a href="https://a.com/x">文档</a></p>')
    assert "文档" in out and "https://a.com/x" not in out and "<a " not in out


def test_text_command_mapped_to_cjk_font():
    from feishu2pub.wechat_convert import mathtext_source
    assert mathtext_source(r"\text{KV 字节} = \sum_{\text{层}} b") == r"\mathsf{KV\ 字节} = \sum_{\mathsf{层}} b"


def test_render_formula_with_chinese_text():
    from feishu2pub.wechat_convert import render_formula
    png = render_formula(r"\text{KV 字节} = \sum_{\text{层}} 2 \times n_{kv}")
    with Image.open(io.BytesIO(png)) as im:
        assert im.width > 100


def test_le_ge_aliases_mapped():
    from feishu2pub.wechat_convert import mathtext_source, render_formula
    assert mathtext_source(r"a \le b \ge c \leq d") == r"a \leq b \geq c \leq d"
    render_formula(r"b\,(\beta P + K P_a) \le BW_{eff}")


def test_bmod_mapped():
    from feishu2pub.wechat_convert import mathtext_source, render_formula
    tex = r"x = s \times \mathrm{0x83DCD12D} \bmod 2^{32}"
    assert "bmod" not in mathtext_source(tex)
    render_formula(tex)


def test_underbrace_mapped_to_underset():
    from feishu2pub.wechat_convert import mathtext_source, render_formula
    tex = r"\underbrace{28.7}_{\text{多处理的像素}} \times \underbrace{1.98}_{\text{每像素}}"
    assert "underbrace" not in mathtext_source(tex)
    render_formula(tex)


def test_cut_at_heading_drops_tail_and_appends_note():
    from feishu2pub.wechat_convert import cut_at_heading
    html = '<h2 style="x">1. 正文</h2><p>a</p><h2 style="x">6. 附录 A：x</h2><p>b</p><h2>7. 参考</h2>'
    out, n = cut_at_heading(html, "附录 A", "见原文")
    assert "附录" not in out.replace("见原文", "") and "<p>a</p>" in out and out.endswith("见原文</p>")
    assert n == 2
    assert cut_at_heading(html, "不存在", "x") == (html, 0)
