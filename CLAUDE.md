# feishu2zhihu

把飞书文档（docx 或 wiki 链接）导入成知乎文章草稿。只建或更新草稿，永远不发布；用户在知乎编辑器里人工审阅后自己点发布。

## 常用命令

```bash
python3 -m feishu2zhihu.cli <飞书URL>             # 导入或更新草稿
python3 -m feishu2zhihu.cli <飞书URL> --dry-run   # 只拉取和转换，不碰知乎，输出 out/<doc_id>/article.html
python3 -m feishu2zhihu.cli <飞书URL> --new       # 忽略已有映射，新建一篇草稿
python3 -m pytest -q tests                        # 转换器单测（离线）
```

Python 3.11，依赖见 `requirements.txt`（`httpx`、`Pillow`），外加全局安装的 `lark-cli`（@larksuite/cli）。

## 结构

- `feishu2zhihu/feishu.py`：调用 `lark-cli`，`docs +fetch --doc-format xml` 拉取 DocxXML，`docs +media-download` 下载图片和画板。
- `feishu2zhihu/convert.py`：DocxXML 转知乎 HTML 的纯函数。图片通过回调解析，无法表示的格式会降级，并记入 `Converter.warnings`。
- `feishu2zhihu/images.py`：画板裁白边，转无损 PNG。
- `feishu2zhihu/zhihu.py`：最小知乎客户端，只用 Cookie，包括草稿增改、图片上传（OSS 直传）。
- `feishu2zhihu/cli.py`：串起整个流程，4 线程并发处理图片。

## 配置与状态（都不提交）

- `.env`：`ZHIHU_Z_C0`、`ZHIHU_XSRF`、`ZHIHU_D_C0`，取自浏览器 Cookie；`LARK_PROFILE` 为能读到文档的 lark-cli profile，留空用默认。模板见 `.env.example`。不要打印或回显这些值。
- `state.json`：`docs` 记录 飞书 document_id → 知乎 article_id，重复运行时据此更新同一篇草稿；`images` 记录图片 md5 → 知乎 src，避免重复上传。
- `out/`、`samples/`：拉取结果和生成的 HTML。

## 已验证的平台行为

- 知乎草稿接口只需 Cookie 和 `x-xsrftoken` 请求头，不需要 `x-zse-96` 签名。
- 草稿阶段图片状态一直是 `processing`，属于正常现象。知乎保存时会把图片地址改写成 `pic-private.zhihu.com`，正文显示 `~resize:1440`，原图在 `data-original-src`（`~resize:0`）。公开的 picx 地址在发布前返回 403。
- 公式写成 `<img eeimg="1" src="https://www.zhihu.com/equation?tex=...">`。知乎保存后会清空 src，只保留 alt 里的源码。独立公式在末尾加 `\\`。
- 知乎只有两级标题。飞书最浅一级标题映射为 `<h2>`，下一级为 `<h3>`，更深的转成加粗段落。
- 表格必须带 `data-draft-node="block" data-draft-type="table"` 属性；合并单元格会拆开，空位补成空单元格。
- 飞书报 131006 或 3380004 权限错误时，通常是 lark-cli 当前 profile 的账号看不到这篇文档。先检查 `.env` 里的 `LARK_PROFILE`，不要反复重试或重新授权。

## 约定

- 不要调用知乎发布接口（`/api/v4/content/publish`），除非用户明确要求。
- 修改转换规则时，先在 `tests/test_convert.py` 加用例。示例文档只覆盖部分标签，规格见 `lark-cli skills read lark-doc/references/lark-doc-xml.md`。
- 改动后跑一次 `--dry-run` 确认无报错，再写入草稿，并通过 `Zhihu.get_draft()` 读回核对知乎实际保存的内容。
