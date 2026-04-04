#!/usr/bin/env python3
"""账号池管理脚本 — add / remove / list / sync-profiles

用法:
  python manage_pool.py add --url "https://www.douyin.com/user/xxx"
  python manage_pool.py add --sec-user-id "xxx"
  python manage_pool.py remove --nickname "张三"
  python manage_pool.py remove --sec-user-id "xxx"
  python manage_pool.py list
  python manage_pool.py sync-profiles
  python manage_pool.py count
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ── 公共配置 ──────────────────────────────────────────
from _config import DATA_DIR, POOL_FILE, DEFAULT_HEADERS, TIKHUB_BASE_URL, RATE_LIMIT_RETRIES, PAGE_INTERVAL, get_tikhub_api_key

# ── 工具函数 ──────────────────────────────────────────

def _load_pool() -> list[dict]:
    if POOL_FILE.exists():
        return json.loads(POOL_FILE.read_text("utf-8"))
    return []


def _save_pool(accounts: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    POOL_FILE.write_text(json.dumps(accounts, ensure_ascii=False, indent=2), "utf-8")


def _extract_sec_uid(text: str) -> str:
    """从抖音主页 URL 或文本中提取 sec_user_id。"""
    text = text.strip()
    # 直接是 sec_user_id（纯字母数字下划线横线，长度较长）
    if re.match(r"^MS4wLjAB[\w\-]{40,}$", text):
        return text
    # URL 格式: https://www.douyin.com/user/MS4wLjAB...
    m = re.search(r"/user/(MS4wLjAB[\w\-]+)", text)
    if m:
        return m.group(1)
    return ""


def _fetch_douyin_profile(sec_uid: str) -> dict | None:
    """通过抖音公开接口获取用户资料。"""
    try:
        resp = requests.get(
            "https://www.iesdouyin.com/web/api/v2/user/info/",
            params={"sec_uid": sec_uid},
            headers=DEFAULT_HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        return payload.get("user_info")
    except Exception as e:
        print(f"[WARN] 抖音资料拉取失败: {e}", file=sys.stderr)
        return None


def _fetch_douyin_profile_via_tikhub(sec_uid: str, api_key: str) -> dict | None:
    """通过 TikHub 获取用户资料（备用方案）。"""
    try:
        resp = requests.get(
            f"{TIKHUB_BASE_URL}/api/v1/douyin/web/fetch_user_profile",
            params={"sec_user_id": sec_uid},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") == 200:
            data = payload.get("data", {})
            user = data.get("user", {}) if isinstance(data, dict) else {}
            if user:
                return {
                    "nickname": user.get("nickname", ""),
                    "avatar_url": user.get("avatar_larger", {}).get("url_list", [""])[0] if isinstance(user.get("avatar_larger"), dict) else "",
                    "followers": user.get("follower_count", 0),
                    "following": user.get("following_count", 0),
                    "posts_count": user.get("aweme_count", 0),
                    "signature": user.get("signature", ""),
                }
    except Exception as e:
        print(f"[WARN] TikHub 资料拉取失败: {e}", file=sys.stderr)
    return None


def _fetch_latest_aweme_id(sec_uid: str, api_key: str) -> str:
    """抓取账号最新一条视频的 aweme_id，用于初始化增量基线。"""
    try:
        last_error = None
        for attempt, retry in enumerate((0.0, *RATE_LIMIT_RETRIES), start=1):
            if retry > 0:
                time.sleep(retry)
            resp = requests.get(
                f"{TIKHUB_BASE_URL}/api/v1/douyin/app/v3/fetch_user_post_videos",
                params={"sec_user_id": sec_uid, "max_cursor": 0, "count": 1},
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30,
            )
            if resp.status_code == 429:
                last_error = Exception("429")
                continue
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("code") != 200:
                return ""
            data = payload.get("data", {})
            items = data.get("aweme_list") or data.get("aweme_list_v2") or data.get("items") or data.get("list") or []
            if items and isinstance(items, list) and isinstance(items[0], dict):
                aweme_id = str(items[0].get("aweme_id") or items[0].get("awemeId") or "").strip()
                return aweme_id
            return ""
    except Exception as e:
        print(f"[WARN] 初始化最新视频ID失败: {e}", file=sys.stderr)
    return ""


# ── 命令实现 ──────────────────────────────────────────

def cmd_add(args) -> None:
    sec_uid = ""
    if args.url:
        sec_uid = _extract_sec_uid(args.url)
        if not sec_uid:
            print(json.dumps({"ok": False, "error": "无法从 URL 中提取 sec_user_id，请检查链接格式"}, ensure_ascii=False))
            return
    elif args.sec_user_id:
        sec_uid = args.sec_user_id.strip()
    else:
        print(json.dumps({"ok": False, "error": "请提供 --url 或 --sec-user-id"}, ensure_ascii=False))
        return

    pool = _load_pool()

    # 检查重复
    for acc in pool:
        if acc.get("sec_user_id") == sec_uid:
            print(json.dumps({"ok": False, "error": f"账号「{acc.get('nickname', sec_uid)}」已在监控池中"}, ensure_ascii=False))
            return

    # 拉取资料
    profile_info = _fetch_douyin_profile(sec_uid)
    if not profile_info:
        api_key = get_tikhub_api_key()
        if api_key:
            profile_info = _fetch_douyin_profile_via_tikhub(sec_uid, api_key)

    nickname = ""
    avatar_url = ""
    followers = 0
    posts_count = 0
    signature = ""

    if profile_info:
        nickname = str(profile_info.get("nickname") or "").strip()
        if not nickname:
            nickname = str(profile_info.get("unique_id") or "").strip()
        avatar_url = str(
            profile_info.get("avatar_larger", {}).get("url_list", [""])[0]
            if isinstance(profile_info.get("avatar_larger"), dict)
            else profile_info.get("avatar_url", "")
        ).strip()
        followers = int(profile_info.get("mplatform_followers_count") or profile_info.get("follower_count") or profile_info.get("followers") or 0)
        posts_count = int(profile_info.get("aweme_count") or profile_info.get("posts_count") or 0)
        signature = str(profile_info.get("signature") or "").strip()

    # 初始化：抓取最新视频 ID 作为增量基线
    api_key = get_tikhub_api_key()
    latest_aweme_id = ""
    if api_key:
        latest_aweme_id = _fetch_latest_aweme_id(sec_uid, api_key)

    account = {
        "sec_user_id": sec_uid,
        "nickname": nickname or sec_uid[:12],
        "avatar_url": avatar_url,
        "followers": followers,
        "posts_count": posts_count,
        "signature": signature,
        "profile_url": f"https://www.douyin.com/user/{sec_uid}",
        "added_at": datetime.now().isoformat(),
        "last_sync_time": "",
        "last_cursor": "0",
        "last_aweme_id": latest_aweme_id,
    }

    pool.append(account)
    _save_pool(pool)

    init_msg = f"（基线视频ID: {latest_aweme_id}）" if latest_aweme_id else "（未初始化基线，首次监控将全量拉取）"
    print(json.dumps({
        "ok": True,
        "account": account,
        "total": len(pool),
        "message": f"已添加「{account['nickname']}」到监控池，当前共 {len(pool)} 个账号 {init_msg}",
    }, ensure_ascii=False))


def cmd_remove(args) -> None:
    pool = _load_pool()

    if args.sec_user_id:
        target_id = args.sec_user_id.strip()
        pool = [a for a in pool if a.get("sec_user_id") != target_id]
    elif args.nickname:
        name = args.nickname.strip()
        pool = [a for a in pool if name not in a.get("nickname", "")]
    else:
        print(json.dumps({"ok": False, "error": "请提供 --nickname 或 --sec-user-id"}, ensure_ascii=False))
        return

    _save_pool(pool)
    print(json.dumps({
        "ok": True,
        "total": len(pool),
        "message": f"已移除，当前共 {len(pool)} 个账号",
    }, ensure_ascii=False))


def cmd_list(args) -> None:
    pool = _load_pool()
    for i, acc in enumerate(pool, 1):
        sync_status = "已同步" if acc.get("last_sync_time") else "未同步"
        print(f"{i}. {acc['nickname']}  |  粉丝: {acc.get('followers', 0):,}  |  作品: {acc.get('posts_count', 0)}  |  {sync_status}")
    if not pool:
        print("（空）监控池中暂无账号")


def cmd_sync_profiles(args) -> None:
    pool = _load_pool()
    if not pool:
        print(json.dumps({"ok": False, "error": "监控池为空"}, ensure_ascii=False))
        return

    updated = 0
    failed = 0
    for acc in pool:
        sec_uid = acc.get("sec_user_id", "")
        if not sec_uid:
            failed += 1
            continue

        profile_info = _fetch_douyin_profile(sec_uid)
        if profile_info:
            acc["nickname"] = str(profile_info.get("nickname") or acc.get("nickname", "")).strip()
            acc["followers"] = int(profile_info.get("mplatform_followers_count") or profile_info.get("follower_count") or 0)
            acc["posts_count"] = int(profile_info.get("aweme_count") or 0)
            acc["signature"] = str(profile_info.get("signature") or "").strip()
            updated += 1
        else:
            failed += 1
        time.sleep(1)

    _save_pool(pool)
    print(json.dumps({
        "ok": True,
        "total": len(pool),
        "updated": updated,
        "failed": failed,
        "message": f"资料刷新完成：成功 {updated}，失败 {failed}，共 {len(pool)} 个",
    }, ensure_ascii=False))


def cmd_count(args) -> None:
    pool = _load_pool()
    print(json.dumps({"ok": True, "total": len(pool)}, ensure_ascii=False))


# ── 入口 ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="账号池管理")
    sub = parser.add_subparsers(dest="command")

    # add
    p_add = sub.add_parser("add")
    p_add.add_argument("--url", help="抖音主页链接")
    p_add.add_argument("--sec-user-id", help="sec_user_id")

    # remove
    p_rm = sub.add_parser("remove")
    p_rm.add_argument("--nickname", help="昵称（模糊匹配）")
    p_rm.add_argument("--sec-user-id", help="sec_user_id")

    sub.add_parser("list")
    sub.add_parser("sync-profiles")
    sub.add_parser("count")

    args = parser.parse_args()

    commands = {
        "add": cmd_add,
        "remove": cmd_remove,
        "list": cmd_list,
        "sync-profiles": cmd_sync_profiles,
        "count": cmd_count,
    }

    fn = commands.get(args.command)
    if fn:
        fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
