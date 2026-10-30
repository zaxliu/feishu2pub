---
name: feishu2pub
description: >
  Import a Feishu (飞书) docx or wiki document as a draft on Zhihu (知乎) or a WeChat Official
  Account (微信公众号), with text, images, whiteboards, tables, formulas and links converted
  automatically. Use when the user wants to publish, sync, import or move a Feishu doc to Zhihu or
  WeChat, update an existing draft from Feishu, or troubleshoot the feishu2pub tool. Triggers:
  飞书导入知乎, 飞书发知乎, 同步到知乎, 知乎草稿, 发公众号, 同步到微信, 公众号草稿, feishu to zhihu, feishu to wechat.
---

# feishu2pub

Repo: the feishu2pub checkout this skill lives in (`skills/feishu2pub/` inside it; usually symlinked into `~/.claude/skills/`). Resolve the symlink to find the repo root, and read its `CLAUDE.md` before changing code. GitHub: `zaxliu/feishu2pub`.

The tool only creates or updates drafts. Never publish on the user's behalf; they review in the editor and publish manually. Personal-entity WeChat accounts have no publish API anyway.

## Run

```bash
cd <repo root>
python3 -m feishu2pub zhihu  '<feishu URL>' --dry-run   # optional: local conversion only
python3 -m feishu2pub zhihu  '<feishu URL>'             # create or update the Zhihu draft
python3 -m feishu2pub wechat '<feishu URL>'             # create or update the WeChat draft
```

- `--drop-section TEXT` (both subcommands, repeatable) leaves out the section whose h1 contains TEXT, e.g. `--drop-section 附录` to skip the appendix but keep 参考资料; later headings are renumbered. `--cut-from` (WeChat only) instead drops that section and everything after it.
- Re-running on the same doc updates the same draft (mapping in `state.json`; WeChat under the `wechat` key). Use `--new` for a fresh draft.
- Report to the user: the draft location (Zhihu edit URL, or 公众号后台 → 内容管理 → 草稿箱), the image count, and every line under `needs review`.
- Before reporting success, read the draft back (`Zhihu.get_draft(article_id)` / `Wechat.get_draft(media_id)`) and check that images, tables and formulas survived.
- Before syncing, grep the Feishu doc for `feishu.cn` links. Readers can't open Feishu docs (company wiki links such as `horizonrobotics.feishu.cn` also leak internal docs). Replace each one with the published Zhihu article URL; `state.json` `docs.<doc_id>.article_id` maps Feishu docs to Zhihu articles. Fix the Feishu source with `block_replace`, so later syncs don't bring the old link back.
- If the article is already published on Zhihu, don't resync it: a resync overwrites hand edits the user made in the editor (for example, a deleted appendix). Replace the link in place with `get_draft` → `str.replace` → `patch_draft`, and do the same for the WeChat draft with `get_draft` → `update_draft`. Its `content` also contains the URL as plain text after the link. Then tell the user to open the Zhihu edit page and click 发布; until they do, the live version keeps the old link.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Feishu `131006` / `3380004` permission error | The lark-cli profile can't see the doc. Check `LARK_PROFILE` in `.env` (`lark-cli auth list` shows profiles). If the doc is outside that account, ask the user to share it. |
| Zhihu HTTP 401/403 on `me` or draft calls | Cookies expired. Ask the user to refill `ZHIHU_Z_C0` / `ZHIHU_XSRF` / `ZHIHU_D_C0` in `.env` from browser DevTools. Never ask them to paste the values in chat. |
| WeChat warns `over WeChat's 20000 limit` | Most often the URLs printed after each link. Rerun with `--no-link-urls --source-url <Zhihu article URL>` so readers get links via 阅读原文. |
| WeChat `errcode=40164` | Public IP changed. The errmsg shows the new IP; ask the user to add it to the API IP whitelist in 微信开发者平台. |
| WeChat `40001` / `40125` | AppSecret wrong or reset. Ask the user to refill `WECHAT_APPSECRET` in `.env`. |
| `[图片缺失：TOKEN]` in the draft | Download or upload failed for that token. Rerun; uploads are cached by md5, so only the failed ones redo. |
| Mapped draft deleted on the platform | The CLI falls back to creating a new draft automatically. |
| Tables show 「该式样无法显示」 | Zhihu app limitation (2026-10-23): the app editor can't render draft tables, the web editor shows them fine. Not a conversion bug; tell the user to review and publish from the web. |
| User wants 「包含 AI 辅助创作」 on an article | The article draft API ignores disclaimer fields (tested 2026-10-23); it is only set by the publish call, which we never make. Remind the user to tick 创作声明 in the web editor before publishing. |
| Unknown Feishu block warning | Add a rule in `feishu2pub/convert.py` (or `wechat_convert.py`), with a test first. |
