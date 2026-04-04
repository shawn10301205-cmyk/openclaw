#!/usr/bin/env python3
"""增量监控新发作品 — 遍历账号池，只抓取上次同步后的新作品。

改进版：
  - 添加账号时已初始化 last_aweme_id，增量翻页遇到该 ID 即停止
  - 缓存按天分文件（2026-04-03.json），自动清理过期数据
  - 不再无限积累历史数据

用法:
  python monitor_new_posts.py
  python monitor_new_posts.py --account "张三"

输出 JSON: { ok, new_posts, accounts_checked, errors, posts: [...] }
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

from _config import (
    DATA_DIR, POOL_FILE, CACHE_DIR,
    TIKHUB_BASE_URL, PAGE_INTERVAL, RATE_LIMIT_RETRIES, DEFAULT_HEADERS,
    CACHE_KEEP_DAYS,
    get_tikhub_api_key,
)


# ── 工具 ──────────────────────────────────────────────

def _load_pool() -> list[dict]:
    if POOL_FILE.exists():
        return json.loads(POOL_FILE.read_text("utf-8"))
    return []


def _save_pool(pool: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    POOL_FILE.write_text(json.dumps(pool, ensure_ascii=False, indent=2), "utf-8")


def _account_cache_dir(sec_uid: str) -> Path:
    safe_name = re.sub(r"[^\w\-]", "_", sec_uid[:20])
    return CACHE_DIR / safe_name


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _load_today_posts(sec_uid: str) -> list[dict]:
    """加载今天的缓存帖子。"""
    cache_file = _account_cache_dir(sec_uid) / f"{_today_str()}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text("utf-8"))
    return []


def _save_today_posts(sec_uid: str, posts: list[dict]) -> None:
    """保存到今天的缓存文件。"""
    cache_dir = _account_cache_dir(sec_uid)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{_today_str()}.json"
    cache_file.write_text(json.dumps(posts, ensure_ascii=False, indent=2), "utf-8")


def _cleanup_old_cache(sec_uid: str) -> int:
    """删除超过 CACHE_KEEP_DAYS 天的缓存文件，返回删除数量。"""
    cache_dir = _account_cache_dir(sec_uid)
    if not cache_dir.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=CACHE_KEEP_DAYS)
    removed = 0
    for f in cache_dir.glob("*.json"):
        # 文件名格式: 2026-04-03.json
        try:
            file_date = datetime.strptime(f.stem, "%Y-%m-%d")
            if file_date < cutoff:
                f.unlink()
                removed += 1
        except ValueError:
            # 兼容旧的 posts.json — 也清掉
            if f.name == "posts.json":
                f.unlink()
                removed += 1
    return removed


def _request_tikhub(path: str, params: dict, api_key: str) -> dict:
    last_error = None
    for attempt, retry in enumerate((0.0, *RATE_LIMIT_RETRIES), start=1):
        if retry > 0:
            time.sleep(retry)
        resp = requests.get(
            f"{TIKHUB_BASE_URL}{path}",
            params=params,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        if resp.status_code == 429:
            last_error = Exception(f"429 Too Many Requests: {resp.url}")
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
    raw = payload.get("aweme_list") or payload.get("aweme_list_v2") or payload.get("items") or payload.get("list") or []
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
        "cover_url": _pick_cover(aweme),
        "fetched_at": datetime.now().isoformat(),
    }


def _pick_cover(aweme: dict) -> str:
    video = aweme.get("video") or {}
    for key in ("cover", "origin_cover", "dynamic_cover"):
        cover = video.get(key)
        if isinstance(cover, dict):
            urls = cover.get("url_list") or []
            if urls:
                return str(urls[0])
    return ""


# ── 核心逻辑 ──────────────────────────────────────────

def fetch_new_posts_for_account(account: dict, api_key: str) -> dict:
    """为单个账号抓取新作品（增量）。遇到 last_aweme_id 即停止。"""
    sec_uid = account.get("sec_user_id", "")
    nickname = account.get("nickname", "")
    last_aweme_id = account.get("last_aweme_id", "")

    # 清理过期缓存
    _cleanup_old_cache(sec_uid)

    # 加载今天已有的缓存
    today_posts = _load_today_posts(sec_uid)
    existing_ids = {p.get("aweme_id") for p in today_posts}

    new_posts = []
    cursor = "0"
    max_pages = 5  # 增量最多翻5页
    seen_cursors = set()
    page = 0
    hit_baseline = False

    while page < max_pages:
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
            print(f"[WARN] {nickname} 第{page+1}页抓取失败: {e}", file=sys.stderr)
            break

        page += 1
        for item in items:
            post = _normalize_post(item)
            aid = post["aweme_id"]

            # 遇到基线视频ID，说明之后的都是旧的，停止
            if aid and last_aweme_id and aid == last_aweme_id:
                hit_baseline = True
                break

            if not aid or aid in existing_ids:
                continue
            new_posts.append(post)
            existing_ids.add(aid)

        if hit_baseline:
            break
        if not has_more or not items:
            break
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
        time.sleep(PAGE_INTERVAL)

    # 合并新帖到今天的缓存（新的在前）
    all_today = new_posts + today_posts
    _save_today_posts(sec_uid, all_today)

    # 更新账号同步状态
    account["last_sync_time"] = datetime.now().isoformat()
    if new_posts:
        # 更新基线为最新的视频 ID
        account["last_aweme_id"] = new_posts[0]["aweme_id"]

    return {
        "nickname": nickname,
        "new_count": len(new_posts),
        "today_total": len(all_today),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", help="只监控指定昵称的账号")
    args = parser.parse_args()

    api_key = get_tikhub_api_key()

    pool = _load_pool()
    if not pool:
        print(json.dumps({"ok": False, "error": "监控池为空，请先添加账号"}, ensure_ascii=False))
        sys.exit(1)

    # 筛选目标账号
    targets = pool
    if args.account:
        targets = [a for a in pool if args.account in a.get("nickname", "")]
        if not targets:
            print(json.dumps({"ok": False, "error": f"未找到包含「{args.account}」的账号"}, ensure_ascii=False))
            sys.exit(1)

    results = []
    errors = []
    all_new_posts = []

    for acc in targets:
        nickname = acc.get("nickname", "")
        sec_uid = acc.get("sec_user_id", "")
        try:
            result = fetch_new_posts_for_account(acc, api_key)
            results.append(result)
            # 读取新作品
            if result["new_count"] > 0:
                today_posts = _load_today_posts(sec_uid)
                all_new_posts.extend(today_posts[:result["new_count"]])
        except Exception as e:
            errors.append(f"{nickname}: {e}")
        time.sleep(1)

    # 保存更新的 pool
    _save_pool(pool)

    output = {
        "ok": True,
        "accounts_checked": len(targets),
        "new_posts_total": sum(r["new_count"] for r in results),
        "errors": errors,
        "results": results,
        "posts": all_new_posts,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
