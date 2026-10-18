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
