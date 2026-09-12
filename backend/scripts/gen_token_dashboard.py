"""CLI：從 Linkin 計費庫生成 Token 用量看板 HTML。"""
from __future__ import annotations

import argparse
from pathlib import Path

from backend.billing.context import default_anonymous_user
from backend.billing.token_dashboard.service import generate_token_dashboard_html


def main() -> None:
    ap = argparse.ArgumentParser(description="Linkin Token 用量看板生成器")
    ap.add_argument("--user", default="", help="帳號 user_id（預設匿名/當前環境）")
    ap.add_argument("--days", type=int, default=90, help="回溯天數（1–365）")
    ap.add_argument("--out", default="token-dashboard.html", help="輸出 HTML 路徑")
    args = ap.parse_args()
    uid = (args.user or default_anonymous_user()).strip()
    html = generate_token_dashboard_html(uid, days=args.days)
    out = Path(args.out)
    out.write_text(html, encoding="utf-8")
    print(f"written: {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
