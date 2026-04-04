#!/usr/bin/env python3
"""爆款检测 — 扫描已缓存作品，检测最近 N 小时内发布的破万赞作品。

用法:
  python check_viral.py                    # 默认：最近1小时、1万赞
  python check_viral.py --hours 2 --min-likes 50000   # 最近2小时、5万赞
  python check_viral.py --all              # 不限时间，只看点赞数

输出 JSON: { ok, viral_count, viral_posts: [...] }
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ── 常量 ──────────────────────────────────────────────

DATA_DIR = Path(os.environ.get("ACCOUNT_MONITOR_DATA_DIR", str(Path.home() / ".account-monitor")))
CACHE_DIR = DATA_DIR / "posts-cache"
ALERTS_FILE = DATA_DIR / "alerts.json"


# ── 工具 ──────────────────────────────────────────────

def _load_all_posts() -> list[dict]:
    """从缓存目录加载所有账号的作品。"""
    all_posts = []
    if not CACHE_DIR.exists():
        return all_posts
    for account_dir in CACHE_DIR.iterdir():
        if not account_dir.is_dir():
            continue
        posts_file = account_dir / "posts.json"
        if posts_file.exists():
            posts = json.loads(posts_file.read_text("utf-8"))
            all_posts.extend(posts)
    return all_posts


def _parse_time(time_str: str) -> datetime | None:
    """解析各种时间格式。"""
    if not time_str:
        return None
    time_str = str(time_str).strip()
    # ISO 格式
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(time_str[:26], fmt)
        except ValueError:
            continue
    # Unix 时间戳
    if time_str.isdigit():
        try:
            return datetime.fromtimestamp(int(time_str))
        except Exception:
            pass
    return None


def _save_alerts(alerts: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ALERTS_FILE.write_text(json.dumps(alerts, ensure_ascii=False, indent=2), "utf-8")


def _load_alerts() -> list[dict]:
    if ALERTS_FILE.exists():
        return json.loads(ALERTS_FILE.read_text("utf-8"))
    return []


# ── 核心逻辑 ──────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=1.0, help="检测最近 N 小时内发布的作品（0=不限时间）")
    parser.add_argument("--min-likes", type=int, default=10000, help="最低点赞数阈值")
    parser.add_argument("--all", action="store_true", help="不限发布时间，只按点赞筛选")
    parser.add_argument("--account", help="只检测指定昵称的账号")
    args = parser.parse_args()

    all_posts = _load_all_posts()
    if not all_posts:
        print(json.dumps({"ok": True, "viral_count": 0, "viral_posts": [], "message": "暂无缓存作品，请先运行 monitor_new_posts.py"}, ensure_ascii=False))
        return

    now = datetime.now()
    time_limit = now - timedelta(hours=args.hours) if args.hours > 0 and not args.all else None

    # 筛选爆款
    viral_posts = []
    for post in all_posts:
        # 点赞数过滤
        if post.get("digg_count", 0) < args.min_likes:
            continue

        # 时间过滤
        if time_limit:
            publish_time = _parse_time(post.get("publish_time", ""))
            if not publish_time or publish_time < time_limit:
                # 检查 fetched_at 作为备选
                fetched_time = _parse_time(post.get("fetched_at", ""))
                if not fetched_time or fetched_time < time_limit:
                    continue

        # 账号过滤
        if args.account and args.account not in post.get("author", ""):
            continue

        viral_posts.append({
            "author": post.get("author", ""),
            "title": post.get("title", ""),
            "aweme_id": post.get("aweme_id", ""),
            "share_url": post.get("share_url", ""),
            "publish_time": post.get("publish_time", ""),
            "digg_count": post.get("digg_count", 0),
            "comment_count": post.get("comment_count", 0),
            "collect_count": post.get("collect_count", 0),
            "share_count": post.get("share_count", 0),
        })

    # 按点赞降序排列
    viral_posts.sort(key=lambda x: x["digg_count"], reverse=True)

    # 记录到告警文件
    existing_alerts = _load_alerts()
    existing_ids = {a.get("aweme_id") for a in existing_alerts}
    new_alerts = [p for p in viral_posts if p["aweme_id"] not in existing_ids]
    all_alerts = new_alerts + existing_alerts
    _save_alerts(all_alerts[:500])  # 最多保留500条

    output = {
        "ok": True,
        "viral_count": len(viral_posts),
        "new_alerts": len(new_alerts),
        "threshold": {"hours": args.hours, "min_likes": args.min_likes},
        "viral_posts": viral_posts,
    }

    # 人类可读输出
    if viral_posts:
        print(f"检测到 {len(viral_posts)} 条爆款作品（{args.min_likes:,}+ 赞）：\n")
        for i, p in enumerate(viral_posts, 1):
            print(f"{i}. [{p['author']}] {p['title'][:50]}")
            print(f"   点赞: {p['digg_count']:,} | 评论: {p['comment_count']:,} | 收藏: {p['collect_count']:,}")
            print(f"   发布: {p['publish_time']}")
            print(f"   链接: {p['share_url']}")
            print()

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
