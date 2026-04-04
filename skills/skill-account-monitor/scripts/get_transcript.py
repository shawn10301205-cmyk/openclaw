#!/usr/bin/env python3
"""获取视频文案 — 优先通过 te.92k.fun 获取语音转写文案，降级用 TikHub。

用法:
  python get_transcript.py --aweme-id "7xxxxxxxxxxxxx"
  python get_transcript.py --url "https://www.douyin.com/video/7xxxxxxxxxxxxx"
  python get_transcript.py --url "1.51 g@b.nd 07/16 VLJ:/ ...  https://v.douyin.com/xxx/ 复制此链接..."
  python get_transcript.py --account "张三" --index 0   # 从缓存中第N条作品获取

输出 JSON: { ok, aweme_id, transcript, title, transcript_source, comments, video_info }
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

from _config import (
    DATA_DIR, CACHE_DIR, TIKHUB_BASE_URL, get_tikhub_api_key,
    TE_92K_API_URL, get_te92k_key,
)


# ── TikHub 工具 ──────────────────────────────────────

def _request_tikhub(path: str, params: dict, api_key: str) -> dict:
    resp = requests.get(
        f"{TIKHUB_BASE_URL}{path}",
        params=params,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 200:
        raise ValueError(str(payload.get("message") or payload))
    data = payload.get("data")
    return data if isinstance(data, dict) else {"items": data}


def _extract_aweme_id(text: str) -> str:
    """从 URL 或文本中提取 aweme_id。"""
    text = text.strip()
    # 直接是 aweme_id（纯数字）
    if re.match(r"^\d{15,}$", text):
        return text
    # URL: https://www.douyin.com/video/7xxxxxxxxx
    m = re.search(r"/video/(\d+)", text)
    if m:
        return m.group(1)
    # 短链接中的 modal_id
    m = re.search(r"modal_id=(\d+)", text)
    if m:
        return m.group(1)
    return text


def _fetch_video_info(aweme_id: str, api_key: str) -> dict:
    """获取视频详情（含文案 desc）— TikHub。"""
    try:
        data = _request_tikhub(
            "/api/v1/douyin/web/fetch_video_info",
            {"aweme_id": aweme_id},
            api_key,
        )
        aweme = data.get("aweme_detail") or data
        if isinstance(aweme, list):
            aweme = aweme[0] if aweme else {}
        return aweme
    except Exception:
        try:
            data = _request_tikhub(
                "/api/v1/douyin/app/v3/fetch_video_info",
                {"aweme_id": aweme_id},
                api_key,
            )
            return data.get("aweme_detail") or data
        except Exception:
            return {}


def _fetch_video_comments(aweme_id: str, api_key: str, count: int = 20) -> list[dict]:
    """获取视频高赞评论 — TikHub。"""
    comments = []
    try:
        data = _request_tikhub(
            "/api/v1/douyin/web/fetch_video_comments",
            {"aweme_id": aweme_id, "cursor": 0, "count": count},
            api_key,
        )
        raw_comments = data.get("comments") or []
        for c in raw_comments:
            if not isinstance(c, dict):
                continue
            user_info = c.get("user") or {}
            comments.append({
                "user": str(user_info.get("nickname") or "匿名").strip(),
                "text": str(c.get("text") or "").strip(),
                "likes": int(c.get("digg_count") or 0),
            })
        comments.sort(key=lambda x: x["likes"], reverse=True)
    except Exception as e:
        print(f"[WARN] 评论获取失败: {e}", file=sys.stderr)
    return comments


# ── te.92k.fun 语音转写 API ──────────────────────────

def _fetch_transcript_92k(url: str) -> dict | None:
    """通过 te.92k.fun 获取视频语音转写文案。

    返回 dict: { transcript, title, source: "92k" }
    失败返回 None。
    """
    try:
        key = get_te92k_key()
        resp = requests.post(
            TE_92K_API_URL,
            json={"key": key, "url": url},
            headers={"Content-Type": "application/json"},
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 200:
            print(f"[WARN] te.92k.fun 返回非200: {payload.get('msg')}", file=sys.stderr)
            return None

        # 提取转写文案
        transcripts = payload.get("transcripts") or []
        transcript_text = ""
        if transcripts and isinstance(transcripts, list):
            transcript_text = transcripts[0].get("text", "")

        # 提取视频信息
        video = payload.get("video") or {}
        title = video.get("title", "")

        # 如果转写文案也在 video.text 里
        if not transcript_text and video.get("text"):
            transcript_text = video["text"]

        if not transcript_text:
            print("[WARN] te.92k.fun 返回空文案", file=sys.stderr)
            return None

        # 积分信息
        ka_info = payload.get("ka_info") or {}
        remaining = ka_info.get("remaining", "?")
        print(f"[INFO] te.92k.fun 转写成功，剩余积分: {remaining}", file=sys.stderr)

        return {
            "transcript": transcript_text,
            "title": title,
            "source": "92k",
        }
    except Exception as e:
        print(f"[WARN] te.92k.fun 调用失败: {e}，将降级到 TikHub", file=sys.stderr)
        return None


# ── 缓存 ─────────────────────────────────────────────

def _find_account_post(nickname: str, index: int) -> dict | None:
    """从缓存中查找指定账号的第 index 条作品。"""
    if not CACHE_DIR.exists():
        return None
    for account_dir in CACHE_DIR.iterdir():
        if not account_dir.is_dir():
            continue
        posts_file = account_dir / "posts.json"
        if not posts_file.exists():
            continue
        posts = json.loads(posts_file.read_text("utf-8"))
        if posts and nickname in posts[0].get("author", ""):
            if 0 <= index < len(posts):
                return posts[index]
            return None
    return None


# ── 核心逻辑 ──────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--aweme-id", help="视频 aweme_id")
    parser.add_argument("--url", help="视频链接（支持分享口令）")
    parser.add_argument("--account", help="从缓存中按昵称查找")
    parser.add_argument("--index", type=int, default=0, help="缓存中的第N条（从0开始）")
    parser.add_argument("--no-comments", action="store_true", help="不获取评论")
    parser.add_argument("--comment-count", type=int, default=20, help="获取评论数量")
    parser.add_argument("--force-tikhub", action="store_true", help="强制使用 TikHub（不走 92k）")
    args = parser.parse_args()

    api_key = get_tikhub_api_key()

    # ── 确定 aweme_id 和 url ──────────────────────────
    aweme_id = ""
    url_for_92k = ""

    if args.url:
        url_for_92k = args.url
        aweme_id = _extract_aweme_id(args.url)
    elif args.aweme_id:
        aweme_id = args.aweme_id
        url_for_92k = f"https://www.douyin.com/video/{aweme_id}"
    elif args.account:
        post = _find_account_post(args.account, args.index)
        if post:
            aweme_id = post.get("aweme_id", "")
            share_url = post.get("share_url", "")
            url_for_92k = share_url or f"https://www.douyin.com/video/{aweme_id}"
        else:
            print(json.dumps({"ok": False, "error": f"未在缓存中找到「{args.account}」的第 {args.index} 条作品"}, ensure_ascii=False))
            sys.exit(1)
    else:
        print(json.dumps({"ok": False, "error": "请提供 --aweme-id、--url 或 --account"}, ensure_ascii=False))
        sys.exit(1)

    if not aweme_id and not url_for_92k:
        print(json.dumps({"ok": False, "error": "无法确定视频 ID"}, ensure_ascii=False))
        sys.exit(1)

    # ── 获取文案 ──────────────────────────────────────
    transcript_text = ""
    video_title = ""
    transcript_source = ""

    # 优先走 te.92k.fun 语音转写
    if not args.force_tikhub and url_for_92k:
        result_92k = _fetch_transcript_92k(url_for_92k)
        if result_92k:
            transcript_text = result_92k["transcript"]
            video_title = result_92k["title"]
            transcript_source = "92k"

    # 拉取 TikHub 视频详情（用于 desc、统计数据、作者信息）
    video_info = {}
    desc = ""
    if aweme_id:
        video_info = _fetch_video_info(aweme_id, api_key)
        desc = str(video_info.get("desc") or "").strip()

    # 如果 92k 没拿到文案，降级用 TikHub desc
    if not transcript_text:
        transcript_text = desc
        transcript_source = "tikhub"
        print("[INFO] 使用 TikHub desc 作为文案", file=sys.stderr)

    if not video_title:
        video_title = desc

    # 话题标签
    text_extra = video_info.get("text_extra") or []
    hashtags = []
    if isinstance(text_extra, list):
        hashtags = [t.get("hashtag_name", "") for t in text_extra if isinstance(t, dict) and t.get("hashtag_name")]

    # 视频统计
    stats = video_info.get("statistics") or {}
    author = video_info.get("author") or {}

    # ── 获取评论 ──────────────────────────────────────
    comments = []
    if not args.no_comments and aweme_id:
        comments = _fetch_video_comments(aweme_id, api_key, count=args.comment_count)

    # ── 组装输出 ──────────────────────────────────────
    output = {
        "ok": True,
        "aweme_id": aweme_id,
        "transcript": transcript_text,
        "title": video_title,
        "desc": desc,
        "transcript_source": transcript_source,
        "hashtags": hashtags,
        "comments": comments,
        "video_info": {
            "author": str(author.get("nickname") or "").strip(),
            "title": video_title,
            "digg_count": int(stats.get("digg_count") or 0),
            "comment_count": int(stats.get("comment_count") or 0),
            "collect_count": int(stats.get("collect_count") or 0),
            "share_count": int(stats.get("share_count") or 0),
            "share_url": str(video_info.get("share_url") or f"https://www.douyin.com/video/{aweme_id}"),
            "duration": int(video_info.get("duration") or 0),
        },
    }

    # ── 人类可读输出 ──────────────────────────────────
    print(f"=== 视频文案（来源: {transcript_source}）===")
    print(transcript_text)
    if video_title and video_title != transcript_text:
        print(f"\n标题: {video_title}")
    if hashtags:
        print(f"\n话题标签: {' '.join('#' + h for h in hashtags if h)}")
    if comments:
        print(f"\n=== 高赞评论（Top {len(comments)}）===")
        for i, c in enumerate(comments[:10], 1):
            print(f"{i}. {c['user']}（{c['likes']}赞）：{c['text']}")

    # JSON 输出
    print("\n" + json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
