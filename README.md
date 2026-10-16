# feishu2zhihu

把飞书文档（docx 或 wiki）导入成知乎文章草稿：文字、图片、画板、表格、公式、链接自动转换，人工在知乎编辑器里审阅后再发布。

工具只建或更新草稿，不会替你发布。

## 能转换什么

| 飞书 | 知乎 |
|---|---|
| 标题 h1 / h2（含自动编号） | 二级 / 三级标题，编号转为文字；更深层级转加粗段落 |
| 段落、加粗、斜体、删除线、行内代码、链接 | 原样 |
| 有序 / 无序列表（可嵌套） | 原样 |
| 表格 | 知乎表格；合并单元格会拆开 |
| 公式（行内 / 独立一行） | 知乎公式 |
| 图片、画板 | 下载后上传到知乎图床；画板自动裁白边、存成无损 PNG |
| 代码块 | `<pre lang>` |
| 高亮块 callout | 引用块（背景色丢失） |
| 分栏、待办、@人、附件等 | 降级处理，并在命令输出里列出供人工检查 |

## 安装

```bash
npm install -g @larksuite/cli     # 飞书侧使用官方 lark-cli，先 lark-cli auth login 登录
pip install -r requirements.txt   # Python 3.11+
cp .env.example .env              # 填入知乎 Cookie
```

知乎 Cookie：浏览器登录知乎后，在 DevTools → Application → Cookies → `https://www.zhihu.com` 里复制 `z_c0`、`_xsrf`、`d_c0`，填进 `.env`。`.env` 已被 gitignore，请勿提交或分享。

## 使用

```bash
python3 -m feishu2zhihu.cli '<飞书链接>' --dry-run   # 只在本地转换，输出 out/<doc_id>/article.html
python3 -m feishu2zhihu.cli '<飞书链接>'             # 写入知乎草稿，打印编辑页链接
python3 -m feishu2zhihu.cli '<飞书链接>' --new       # 不更新旧草稿，新建一篇
```

同一篇飞书文档再次运行会更新同一篇草稿（映射存在本地 `state.json`），图片按内容去重，不会重复上传。

## 测试

```bash
python3 -m pytest -q tests
```

## 注意

- 知乎侧使用的是网页端非公开接口，知乎改版可能导致失效。请只用于自己的账号和自己的内容，并遵守知乎的用户协议。
- 草稿里的图片在发布前是知乎私有链接；正文显示宽度上限为 1440 像素，画板里字太小时建议在飞书里调整画板尺寸或字号。

## 致谢

知乎接口的用法参考并改写自：

- [zhihu_obsidian](https://github.com/zimya/zhihu_obsidian)（0BSD）：草稿创建与更新、图片上传、表格与公式写法
- [zhihu-cli](https://github.com/KrisTHL181/zhihu-cli)（MIT，Copyright (c) 2026 Kris）：图片上传与 OSS 签名

## License

MIT
