# feishu2pub

把飞书文档（docx 或 wiki 链接）导入成知乎文章草稿或微信公众号草稿。只建或更新草稿，永远不发布；用户在编辑器里人工审阅后自己点发布。

## 常用命令

```bash
python3 -m feishu2pub zhihu  <飞书URL>             # 导入或更新知乎草稿
python3 -m feishu2pub wechat <飞书URL>             # 导入或更新公众号草稿
python3 -m feishu2pub zhihu  <飞书URL> --dry-run   # 只拉取和转换，不碰平台，输出 out/<doc_id>/article.html（wechat 为 wechat.html）
python3 -m feishu2pub zhihu  <飞书URL> --new       # 忽略已有映射，新建一篇草稿
python3 -m pytest -q tests                         # 转换器单测（离线）
```

Python 3.11，依赖见 `requirements.txt`（`httpx`、`Pillow`、`matplotlib`），外加全局安装的 `lark-cli`（@larksuite/cli）。

## 结构

共用部分：

- `feishu2pub/__main__.py`：子命令 `zhihu` / `wechat` 的入口。
- `feishu2pub/feishu.py`：调用 `lark-cli`，`docs +fetch --doc-format xml` 拉取 DocxXML，`docs +media-download` 下载图片和画板。
- `feishu2pub/convert.py`：DocxXML 解析和知乎 HTML 输出（`Converter` 基类）。图片通过回调解析，无法表示的格式会降级，并记入 `Converter.warnings`。`equation` / `link` / `figure` 是给其他平台覆盖的钩子。
- `feishu2pub/images.py`：画板裁白边转无损 PNG；`shrink()` 把图片压到微信的 1MB 以内。
- `feishu2pub/state.py`：`.env`、`out/`、`state.json` 的位置和读写。

知乎：`zhihu.py`（最小客户端，只用 Cookie，草稿增改、OSS 直传图片）、`zhihu_cli.py`。

微信：`wechat.py`（官方接口客户端）、`wechat_convert.py`（继承 `Converter`）、`wechat_cli.py`。

## 配置与状态（都不提交）

- `.env`：`ZHIHU_Z_C0`、`ZHIHU_XSRF`、`ZHIHU_D_C0`，取自浏览器 Cookie；`WECHAT_APPID`、`WECHAT_APPSECRET`；`LARK_PROFILE` 为能读到文档的 lark-cli profile，留空用默认。模板见 `.env.example`。不要打印或回显这些值。
- `state.json`：顶层 `docs` / `images` 是知乎的，`wechat` 键下是公众号的同结构映射（另记封面 `thumb_media_id`）。`docs` 记录 飞书 document_id → 知乎 article_id，重复运行时据此更新同一篇草稿；`images` 记录图片 md5 → 知乎 src，避免重复上传。
- `out/`、`samples/`：拉取结果和生成的 HTML。

## 知乎：已验证的平台行为

- 知乎草稿接口只需 Cookie 和 `x-xsrftoken` 请求头，不需要 `x-zse-96` 签名。
- 草稿阶段图片状态一直是 `processing`，属于正常现象。知乎保存时会把图片地址改写成 `pic-private.zhihu.com`，正文显示 `~resize:1440`，原图在 `data-original-src`（`~resize:0`）。公开的 picx 地址在发布前返回 403。
- 公式写成 `<img eeimg="1" src="https://www.zhihu.com/equation?tex=...">`。知乎保存后会清空 src，只保留 alt 里的源码。独立公式在末尾加 `\\`。
- 知乎只有两级标题。飞书最浅一级标题映射为 `<h2>`，下一级为 `<h3>`，更深的转成加粗段落。
- 表格必须带 `data-draft-node="block" data-draft-type="table"` 属性；合并单元格会拆开，空位补成空单元格。
- 飞书报 131006 或 3380004 权限错误时，通常是 lark-cli 当前 profile 的账号看不到这篇文档。先检查 `.env` 里的 `LARK_PROFILE`，不要反复重试或重新授权。

## 微信公众号：已验证的平台行为（个人主体账号）

- `wechat.py` 走官方接口：`stable_token`、`media/uploadimg`（正文图）、`material/add_material`（封面）、`draft/add|update|get`。个人主体没有发布接口权限，只写草稿。需要 `.env` 里的 `WECHAT_APPID`、`WECHAT_APPSECRET`，本机公网 IP 要在微信开发者平台的 API IP 白名单里，否则报 40164。
- `wechat_convert.py` 继承 `Converter`：外链会被微信去掉，改为在链接文字后附纯文本网址；公式用 matplotlib 渲染成 PNG 上传；样式全部写成内联 style。
- 图片必须是小于 1MB 的 jpg/png，`images.shrink()` 负责压缩。微信保存时把 `src` 改成 `data-src`，属于正常现象。
- 2 万字限制按可见文字算，不算标签。
- 映射记在 `state.json` 的 `wechat` 键下；封面默认取第一张图，只上传一次。

## 约定

- 不要调用知乎发布接口（`/api/v4/content/publish`）或微信 `freepublish/*`，除非用户明确要求。
- 修改转换规则时，先在 `tests/test_convert.py` 或 `tests/test_wechat_convert.py` 加用例。示例文档只覆盖部分标签，规格见 `lark-cli skills read lark-doc/references/lark-doc-xml.md`。
- 改动后跑一次 `--dry-run` 确认无报错，再写入草稿，并通过 `Zhihu.get_draft()` / `Wechat.get_draft()` 读回核对平台实际保存的内容。
