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

- Re-running on the same doc updates the same draft (mapping in `state.json`; WeChat under the `wechat` key). Use `--new` for a fresh draft.
- Report to the user: the draft location (Zhihu edit URL, or 公众号后台 → 内容管理 → 草稿箱), the image count, and every line under `needs review`.
- Before reporting success, read the draft back (`Zhihu.get_draft(article_id)` / `Wechat.get_draft(media_id)`) and check that images, tables and formulas survived.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Feishu `131006` / `3380004` permission error | The lark-cli profile can't see the doc. Check `LARK_PROFILE` in `.env` (`lark-cli auth list` shows profiles). If the doc is outside that account, ask the user to share it. |
| Zhihu HTTP 401/403 on `me` or draft calls | Cookies expired. Ask the user to refill `ZHIHU_Z_C0` / `ZHIHU_XSRF` / `ZHIHU_D_C0` in `.env` from browser DevTools. Never ask them to paste the values in chat. |
| WeChat `errcode=40164` | Public IP changed. The errmsg shows the new IP; ask the user to add it to the API IP whitelist in 微信开发者平台. |
| WeChat `40001` / `40125` | AppSecret wrong or reset. Ask the user to refill `WECHAT_APPSECRET` in `.env`. |
| `[图片缺失：TOKEN]` in the draft | Download or upload failed for that token. Rerun; uploads are cached by md5, so only the failed ones redo. |
| Mapped draft deleted on the platform | The CLI falls back to creating a new draft automatically. |
| Unknown Feishu block warning | Add a rule in `feishu2pub/convert.py` (or `wechat_convert.py`), with a test first. |
