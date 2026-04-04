#!/usr/bin/env python3
"""历史高赞筛选 — 从 TikHub 分页拉取指定账号的历史作品，按时间+点赞数筛选。

用法:
  python fetch_history.py --account "张三" --days 30 --min-likes 100000
  python fetch_history.py --account "张三" --all-pages --min-likes 50000
  python fetch_history.py --all-accounts --days 7 --min-likes 10000

输出 JSON: { ok, total_fetched, filtered_count, posts: [...] }
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

from _config import DATA_DIR, POOL_FILE, CACHE_DIR, TIKHUB_BASE_URL, PAGE_INTERVAL, get_tikhub_api_key


# ── 工具 ──────────────────────────────────────────────

def _load_pool() -> list[dict]:
    if POOL_FILE.exists():
        return json.loads(POOL_FILE.read_text("utf-8"))
    return []


def _request_tikhub(path: str, params: dict, api_key: str) -> dict:
    retries = (1.0, 2.0, 4.0)
    last_error = None
    for attempt, retry in enumerate((0.0, *retries), start=1):
        if retry > 0:
            time.sleep(retry)
        resp = requests.get(
            f"{TIKHUB_BASE_URL}{path}",
            params=params,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        if resp.status_code == 429:
            last_error = Exception("429 Too Many Requests")
            continue
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 200:
            raise ValueError(str(payload.get("message") or payload))
        data = payload.get("data")
        return data if isinstance(data, dict) else {"items": data}
    if last_error:
        raise last_error
    raise RuntimeError("TikHub 请求失败")


def _extract_items(payload: dict) -> tuple[list[dict], str, bool]:
    raw = payload.get("aweme_list") or payload.get("aweme_list_v2") or payload.get("items") or []
    items = [i for i in raw if isinstance(i, dict)] if isinstance(raw, list) else []
    cursor = str(payload.get("max_cursor") or payload.get("cursor") or "0")
    has_more = bool(payload.get("has_more"))
    return items, cursor, has_more


def _normalize_post(aweme: dict) -> dict:
    stats = aweme.get("statistics") or {}
    author = aweme.get("author") or {}
    aweme_id = str(aweme.get("aweme_id") or aweme.get("awemeId") or "").strip()
    desc = str(aweme.get("desc") or "").strip()
    create_time = aweme.get("create_time", "")
    if isinstance(create_time, (int, float)) and create_time:
        try:
            create_time = datetime.fromtimestamp(int(create_time)).isoformat()
        except Exception:
            pass

    return {
        "aweme_id": aweme_id,
        "title": desc,
        "desc": desc,
        "author": str(author.get("nickname") or "").strip(),
        "share_url": str(aweme.get("share_url") or f"https://www.douyin.com/video/{aweme_id}").strip(),
        "publish_time": str(create_time),
        "digg_count": int(stats.get("digg_count") or 0),
        "comment_count": int(stats.get("comment_count") or 0),
        "collect_count": int(stats.get("collect_count") or 0),
        "share_count": int(stats.get("share_count") or 0),
    }


def _parse_time(time_str: str) -> datetime | None:
    if not time_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(time_str)[:26], fmt)
        except ValueError:
            continue
    if str(time_str).isdigit():
        try:
            return datetime.fromtimestamp(int(time_str))
        except Exception:
            pass
    return None


def _save_account_posts(sec_uid: str, posts: list[dict]) -> None:
    safe_name = re.sub(r"[^\w\-]", "_", sec_uid[:20])
    cache_file = CACHE_DIR / safe_name / "posts.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(posts, ensure_ascii=False, indent=2), "utf-8")


# ── 核心逻辑 ──────────────────────────────────────────

def fetch_account_history(sec_uid: str, nickname: str, api_key: str, max_pages: int = 50) -> list[dict]:
    """分页拉取账号全部历史作品。"""
    all_posts = []
    cursor = "0"
    seen_cursors = set()

    for page in range(max_pages):
        if cursor in seen_cursors:
            break
        seen_cursors.add(cursor)

        try:
            payload = _request_tikhub(
                "/api/v1/douyin/app/v3/fetch_user_post_videos",
                {"sec_user_id": sec_uid, "max_cursor": int(cursor or 0), "count": 20},
                api_key,
            )
            items, next_cursor, has_more = _extract_items(payload)
        except Exception as e:
            print(f"[WARN] {nickname} 第{page+1}页失败: {e}", file=sys.stderr)
            break

        for item in items:
            all_posts.append(_normalize_post(item))

        if not has_more or not items or not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
        time.sleep(PAGE_INTERVAL)

    return all_posts


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", help="指定账号昵称（模糊匹配）")
    parser.add_argument("--all-accounts", action="store_true", help="拉取所有账号")
    parser.add_argument("--days", type=int, default=30, help="筛选最近 N 天内的作品")
    parser.add_argument("--min-likes", type=int, default=100000, help="最低点赞数")
    parser.add_argument("--max-pages", type=int, default=50, help="每个账号最大翻页数")
    args = parser.parse_args()

    api_key = get_tikhub_api_key()
    if not api_key:
        print(json.dumps({"ok": False, "error": "未配置 TIKHUB_API_KEY"}, ensure_ascii=False))
        sys.exit(1)

    pool = _load_pool()
    if not pool:
        print(json.dumps({"ok": False, "error": "监控池为空"}, ensure_ascii=False))
        sys.exit(1)

    # 筛选目标
    targets = pool
    if args.account:
        targets = [a for a in pool if args.account in a.get("nickname", "")]
        if not targets:
            print(json.dumps({"ok": False, "error": f"未找到「{args.account}」"}, ensure_ascii=False))
            sys.exit(1)
    elif not args.all_accounts:
        print(json.dumps({"ok": False, "error": "请指定 --account 或 --all-accounts"}, ensure_ascii=False))
        sys.exit(1)

    time_limit = datetime.now() - timedelta(days=args.days) if args.days > 0 else None
    all_filtered = []

    for acc in targets:
        nickname = acc.get("nickname", "")
        sec_uid = acc.get("sec_user_id", "")
        print(f"[INFO] 正在拉取 {nickname} 的历史作品...", file=sys.stderr)

        posts = fetch_account_history(sec_uid, nickname, api_key, max_pages=args.max_pages)
        _save_account_posts(sec_uid, posts)

        # 筛选
        for post in posts:
            if post["digg_count"] < args.min_likes:
                continue
            if time_limit:
                pt = _parse_time(post["publish_time"])
                if pt and pt < time_limit:
                    continue
            all_filtered.append(post)

        time.sleep(1)

    # 按点赞降序
    all_filtered.sort(key=lambda x: x["digg_count"], reverse=True)

    # 输出
    print(f"\n筛选结果：{len(all_filtered)} 条 {args.min_likes:,}+ 赞的爆款（最近 {args.days} 天）\n")
    for i, p in enumerate(all_filtered[:50], 1):
        print(f"{i}. [{p['author']}] {p['title'][:60]}")
        print(f"   点赞: {p['digg_count']:,} | 评论: {p['comment_count']:,} | 发布: {p['publish_time'][:16]}")
        print(f"   链接: {p['share_url']}")
        print()

    output = {
        "ok": True,
        "accounts_checked": len(targets),
        "filtered_count": len(all_filtered),
        "threshold": {"days": args.days, "min_likes": args.min_likes},
        "posts": all_filtered,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
