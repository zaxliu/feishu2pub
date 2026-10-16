from feishu2zhihu.convert import Converter, ImageRef, collect_images


def conv(xml, images=None):
    c = Converter(lambda ref: (images or {}).get(ref))
    return c, c.convert(xml)


IMG = {"src": "https://picx.zhimg.com/v2-abc.png", "width": 800, "height": 400}


def test_title_extracted_not_in_body():
    c, out = conv('<title id="x">标题 A</title><p id="1">正文</p>')
    assert c.title == "标题 A"
    assert out == "<p>正文</p>"


def test_headings_shift_to_h2_with_seq_marker():
    c, out = conv('<h1 seq="auto" seq-marker="1.">一</h1><h2>二</h2><h3>三</h3>')
    assert out == "<h2>1. 一</h2><h3>二</h3><p><b>三</b></p>"
    assert any("三级" in w for w in c.warnings)


def test_headings_start_at_h2_still_map_to_h2():
    _, out = conv("<h2>a</h2><h3>b</h3>")
    assert out == "<h2>a</h2><h3>b</h3>"


def test_inline_marks_and_escaping():
    _, out = conv('<p><b>粗</b><em>斜</em><del>删</del><u>下</u><code>a&lt;b</code> 1 &amp; 2</p>')
    assert out == "<p><b>粗</b><i>斜</i><del>删</del>下<code>a&lt;b</code> 1 &amp; 2</p>"


def test_comment_span_dropped_text_kept():
    _, out = conv('<p><span comment-refs="c1">有评论</span>的句子</p>')
    assert out == "<p>有评论的句子</p>"


def test_link():
    _, out = conv('<p><a href="https://a.com/?x=1&amp;y=2">链接</a></p>')
    assert out == '<p><a href="https://a.com/?x=1&amp;y=2">链接</a></p>'


def test_block_and_inline_latex():
    _, out = conv('<p align="center"><latex>a + b</latex></p><p>行内 <latex>x^2</latex> 公式</p>')
    assert '<p><img src="https://www.zhihu.com/equation?tex=a%20%2B%20b%5C%5C"' in out
    assert 'eeimg="1"' in out
    assert "行内 <img src=\"https://www.zhihu.com/equation?tex=x%5E2\"" in out


def test_nested_lists():
    _, out = conv("<ol><li>一<ul><li>子</li></ul></li><li>二</li></ol>")
    assert out == "<ol><li>一<ul><li>子</li></ul></li><li>二</li></ol>"


def test_callout_becomes_blockquote_with_lines():
    c, out = conv('<callout emoji="💡"><p>第一段</p><ul><li>点</li></ul></callout>')
    assert out == "<blockquote>💡 第一段<br/>• 点</blockquote>"
    assert c.warnings


def test_table_header_and_cells():
    xml = (
        "<table><colgroup><col width=\"1\"/></colgroup><thead><tr><th><p>H1</p></th><th><p>H2</p></th></tr></thead>"
        "<tbody><tr><td><p>a</p><p>b</p></td><td><p>c</p></td></tr></tbody></table>"
    )
    _, out = conv(xml)
    assert out.startswith('<table data-draft-node="block" data-draft-type="table"')
    assert "<tr><th>H1</th><th>H2</th></tr><tr><td>a<br/>b</td><td>c</td></tr>" in out


def test_table_merged_cells_padded():
    xml = "<table><tbody><tr><td colspan=\"2\"><p>x</p></td></tr><tr><td><p>a</p></td><td><p>b</p></td></tr></tbody></table>"
    c, out = conv(xml)
    assert "<tr><td>x</td><td></td></tr>" in out
    assert any("合并" in w for w in c.warnings)


def test_whiteboard_resolved_to_figure():
    ref = ImageRef("whiteboard", "WB1")
    _, out = conv('<whiteboard id="1" token="WB1"></whiteboard>', {ref: IMG})
    assert out.startswith('<figure data-size="normal"><img src="https://picx.zhimg.com/v2-abc.png"')
    assert 'data-rawwidth="800"' in out


def test_missing_image_placeholder_and_warning():
    c, out = conv('<img src="TOK"/>')
    assert out == "<p>[图片缺失：TOK]</p>"
    assert c.warnings


def test_image_inside_paragraph_split_out():
    ref = ImageRef("media", "T")
    _, out = conv('<p>前<img src="T"/>后</p>', {ref: IMG})
    assert out.startswith("<p>前</p><figure")
    assert out.endswith("</figure><p>后</p>")


def test_code_block():
    _, out = conv('<pre lang="Python"><code>if a &lt; b:\n    print(1)</code></pre>')
    assert out == '<pre lang="python">if a &lt; b:\n    print(1)</pre>'


def test_collect_images_dedup_in_order():
    xml = '<whiteboard token="A"></whiteboard><img src="B"/><whiteboard token="A"></whiteboard>'
    assert collect_images(xml) == [ImageRef("whiteboard", "A"), ImageRef("media", "B")]


def test_unknown_block_placeholder():
    c, out = conv('<sheet token="s"/>')
    assert out == "<p>[飞书 sheet 块未导出]</p>"
    assert c.warnings
