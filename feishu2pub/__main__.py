"""feishu2pub: import a Feishu doc as a draft on Zhihu or a WeChat Official Account (never publishes).

    python -m feishu2pub zhihu  <feishu URL> [--dry-run] [--new] [--no-trim]
    python -m feishu2pub wechat <feishu URL> [--dry-run] [--new] [--author NAME]
"""

from __future__ import annotations

import sys

from .feishu import FeishuError
from .wechat import WechatError
from .zhihu import ZhihuError

TARGETS = ("zhihu", "wechat")


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in TARGETS:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    if argv[0] == "zhihu":
        from .zhihu_cli import main as run
    else:
        from .wechat_cli import main as run
    try:
        return run(argv[1:])
    except (FeishuError, ZhihuError, WechatError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
