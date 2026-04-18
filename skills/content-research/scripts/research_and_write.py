#!/usr/bin/env python3
"""多源爆款搜集+AI重组文案 — 独立脚本，不依赖其他 skill。

用法:
  python research_and_write.py --url "抖音链接或分享口令"
  python research_and_write.py --keyword "女警 身材 女性力量" --count 10
  python research_and_write.py --batch topics.txt
  python research_and_write.py --keyword "女警" --sort likes --count 5
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

import requests

# ── 配置 ─────────────────────────────────────────────

TIKHUB_API_KEY = os.environ.get(
    "TIKHUB_API_KEY",
    "nY5bGPI1zQ2bpH6aGKKk6TjqPWrKAYR93xfhrWCvaPWgtFDiES2tc3fDGQ==",
).strip()

TE_92K_KEY = os.environ.get(
    "TE_92K_KEY",
    "zyj_cea870128069d6e3a9cce17b504f4dd42",
).strip()

TIKHUB_BASE_URL = "https://api.tikhub.dev"
TE_92K_API_URL = "https://te.92k.fun/user/analysis"

SORT_MAP = {"general": "0", "likes": "2", "newest": "1"}


# ── 视频转写（内联，不依赖 video-to-text）─────────────


def url_to_text(url: str) -> dict:
    """将视频 URL/分享口令转为文本。"""
    try:
        resp = requests.post(
            TE_92K_API_URL,
            json={"key": TE_92K_KEY, "url": url},
            headers={"Content-Type": "application/json"},
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()

        if payload.get("code") != 200:
            return {"ok": False, "error": payload.get("msg") or str(payload)}

        transcripts = payload.get("transcripts") or []
        transcript_text = ""
        if transcripts and isinstance(transcripts, list):
            transcript_text = transcripts[0].get("text", "")

        video = payload.get("video") or {}
        title = video.get("title", "")

        if not transcript_text and video.get("text"):
            transcript_text = video["text"]

        ka_info = payload.get("ka_info") or {}
        remaining = ka_info.get("remaining", -1)

        return {
            "ok": True,
            "transcript": transcript_text,
            "title": title,
            "source": "92k",
            "remaining_points": remaining,
        }

    except requests.exceptions.Timeout:
        return {"ok": False, "error": "请求超时（60秒）"}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"网络错误: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"未知错误: {e}"}


# ── TikHub 搜索（内联）───────────────────────────────


def _tikhub_headers() -> dict:
    return {
        "Authorization": f"Bearer {TIKHUB_API_KEY}",
        "Content-Type": "application/json",
    }


def search_douyin(keyword: str, count: int = 10, sort_type: str = "0") -> list[dict]:
    """搜索抖音相关内容，返回结果列表。"""
    all_results = []
    cursor = 0
    search_id = ""

    while len(all_results) < count:
        batch_size = min(count - len(all_results), 20)
        body = {
            "keyword": keyword,
            "count": batch_size,
            "sort_type": sort_type,
            "cursor": cursor,
            "search_id": search_id,
            "publish_time": "0",
            "filter_duration": "0",
            "content_type": "0",
        }

        try:
            resp = requests.post(
                f"{TIKHUB_BASE_URL}/api/v1/douyin/search/fetch_general_search_v2",
                headers=_tikhub_headers(),
                json=body,
                timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            print(f"[WARN] 搜索请求失败: {e}", file=sys.stderr)
            break

        if payload.get("code") != 200:
            print(f"[WARN] 搜索返回错误: {payload.get('message')}", file=sys.stderr)
            break

        items = payload.get("data", {}).get("business_data", [])
        if not items:
            break

        for item in items:
            aweme = item.get("data", {}).get("aweme_info", {})
            if not aweme:
                continue
            stats = aweme.get("statistics", {})
            all_results.append({
                "aweme_id": aweme.get("aweme_id", ""),
                "desc": aweme.get("desc", ""),
                "author": aweme.get("author", {}).get("nickname", ""),
                "likes": stats.get("digg_count", 0),
                "comments": stats.get("comment_count", 0),
                "shares": stats.get("share_count", 0),
                "url": f"https://www.douyin.com/video/{aweme.get('aweme_id', '')}",
            })

        # 翻页
        has_more = payload.get("data", {}).get("has_more", 0)
        if not has_more:
            break
        cursor = payload.get("data", {}).get("cursor", 0)
        search_id = payload.get("data", {}).get("search_id", "")
        time.sleep(1)

    return all_results[:count]


def get_video_info(aweme_id: str) -> dict | None:
    """通过 aweme_id 获取视频详情。"""
    try:
        resp = requests.get(
            f"{TIKHUB_BASE_URL}/api/v1/douyin/web/fetch_video_info",
            params={"aweme_id": aweme_id},
            headers=_tikhub_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") == 200:
            return payload.get("data", {})
    except Exception:
        pass
    return None


# ── 关键词和标签提取 ──────────────────────────────────


def extract_hashtags(text: str) -> list[str]:
    """提取 # 标签。"""
    return re.findall(r"#(\S+)", text)


def extract_keywords_from_text(text: str) -> str:
    """从文案中提取搜索关键词。"""
    # 去掉标签
    clean = re.sub(r"#\S+", "", text).strip()
    # 提取中文词组（2-6字）
    words = re.findall(r"[\u4e00-\u9fff]{2,6}", clean)
    # 去重保留前5个
    seen = set()
    result = []
    for w in words:
        if w not in seen:
            seen.add(w)
            result.append(w)
    return " ".join(result[:5])


def extract_url_from_share(text: str) -> str | None:
    """从分享口令中提取 URL。"""
    urls = re.findall(r"https?://[^\s]+", text)
    return urls[0] if urls else None


# ── 核心流程 ──────────────────────────────────────────


def research_by_url(url_or_share: str, count: int = 10, sort_type: str = "0") -> dict:
    """通过视频链接/分享口令搜索相关爆款。"""
    # 提取 URL
    url = extract_url_from_share(url_or_share) or url_or_share

    # 转写原视频
    print("[1/3] 转写原视频...", file=sys.stderr)
    transcript_result = url_to_text(url)

    original_desc = ""
    original_transcript = ""
    hashtags = []

    if transcript_result.get("ok"):
        original_transcript = transcript_result.get("transcript", "")
        original_desc = transcript_result.get("title", "")

    # 从分享口令或文案中提取标签
    full_text = url_or_share
    if original_desc:
        full_text = original_desc + " " + full_text
    hashtags = extract_hashtags(full_text)

    # 提取搜索关键词
    search_text = original_desc or url_or_share
    keywords = extract_keywords_from_text(search_text)
    if not keywords and hashtags:
        keywords = " ".join(hashtags[:3])

    print(f"[2/3] 搜索关键词: {keywords}", file=sys.stderr)

    # 搜索相关爆款
    viral_results = search_douyin(keywords, count=count, sort_type=sort_type)

    # 批量转写爆款视频（串行，避免限流）
    print(f"[3/3] 转写 {len(viral_results)} 条爆款视频...", file=sys.stderr)
    for i, item in enumerate(viral_results):
        video_url = f"https://www.douyin.com/video/{item['aweme_id']}"
        t_result = url_to_text(video_url)
        item["transcript"] = t_result.get("transcript", "") if t_result.get("ok") else ""
        item["transcript_ok"] = t_result.get("ok", False)
        print(f"  [{i+1}/{len(viral_results)}] @{item['author']} - 赞{item['likes']}", file=sys.stderr)
        time.sleep(0.5)

    # 按点赞排序
    viral_results.sort(key=lambda x: x.get("likes", 0), reverse=True)

    return {
        "original": {
            "url": url,
            "desc": original_desc,
            "transcript": original_transcript,
            "hashtags": hashtags,
            "keywords_for_search": keywords,
        },
        "viral_videos": viral_results,
        "analysis_ready": True,
        "summary": _build_summary(original_desc, hashtags, viral_results),
    }


def research_by_keyword(keyword: str, count: int = 10, sort_type: str = "0") -> dict:
    """通过关键词直接搜索爆款。"""
    print(f"[1/2] 搜索关键词: {keyword}", file=sys.stderr)

    viral_results = search_douyin(keyword, count=count, sort_type=sort_type)

    print(f"[2/2] 转写 {len(viral_results)} 条爆款视频...", file=sys.stderr)
    for i, item in enumerate(viral_results):
        video_url = f"https://www.douyin.com/video/{item['aweme_id']}"
        t_result = url_to_text(video_url)
        item["transcript"] = t_result.get("transcript", "") if t_result.get("ok") else ""
        item["transcript_ok"] = t_result.get("ok", False)
        print(f"  [{i+1}/{len(viral_results)}] @{item['author']} - 赞{item['likes']}", file=sys.stderr)
        time.sleep(0.5)

    viral_results.sort(key=lambda x: x.get("likes", 0), reverse=True)
    hashtags = extract_hashtags(keyword)

    return {
        "original": {
            "keyword": keyword,
            "hashtags": hashtags,
            "keywords_for_search": keyword,
        },
        "viral_videos": viral_results,
        "analysis_ready": True,
        "summary": _build_summary(keyword, hashtags, viral_results),
    }


def _build_summary(context: str, hashtags: list[str], viral: list[dict]) -> str:
    """构建结构化摘要供 Claude 分析。"""
    lines = [f"主题: {context}", f"标签: {', '.join(hashtags[:5])}", ""]

    if viral:
        lines.append(f"找到 {len(viral)} 条爆款视频，TOP5：")
        for i, v in enumerate(viral[:5]):
            desc = v.get("desc", "")[:60]
            lines.append(
                f"  {i+1}. @{v['author']} | 赞{v['likes']} 评{v['comments']} 转{v['shares']} | {desc}"
            )

    # 统计高频标签
    all_tags = []
    for v in viral:
        all_tags.extend(extract_hashtags(v.get("desc", "")))
    if all_tags:
        from collections import Counter

        tag_counts = Counter(all_tags).most_common(10)
        lines.append("")
        lines.append("高频标签: " + ", ".join(f"#{tag}({cnt})" for tag, cnt in tag_counts))

    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(description="多源爆款搜集+AI重组文案")
    parser.add_argument("--url", help="原视频链接或分享口令")
    parser.add_argument("--keyword", help="直接用关键词搜索爆款")
    parser.add_argument("--batch", help="批量处理文件，每行一个 URL 或关键词")
    parser.add_argument("--count", type=int, default=10, help="搜索数量（默认10）")
    parser.add_argument(
        "--sort",
        choices=["general", "likes", "newest"],
        default="general",
        help="排序方式: general=综合, likes=最多点赞, newest=最新",
    )
    parser.add_argument("--no-transcribe", action="store_true", help="跳过转写（只用文案描述）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（默认输出格式化文本）")
    args = parser.parse_args()

    if not args.url and not args.keyword and not args.batch:
        parser.error("请提供 --url、--keyword 或 --batch")

    sort_type = SORT_MAP.get(args.sort, "0")

    # 单条 URL
    if args.url:
        result = research_by_url(args.url, count=args.count, sort_type=sort_type)
        if args.no_transcribe:
            for v in result.get("viral_videos", []):
                v["transcript"] = ""
                v["transcript_ok"] = False

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["summary"])
            print("\n" + "=" * 50)
            print("以上数据可供 Claude 分析爆款规律并生成衍生文案")
            print("完整 JSON 数据请使用 --json 参数获取")
        return

    # 关键词搜索
    if args.keyword:
        result = research_by_keyword(args.keyword, count=args.count, sort_type=sort_type)
        if args.no_transcribe:
            for v in result.get("viral_videos", []):
                v["transcript"] = ""
                v["transcript_ok"] = False

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["summary"])
            print("\n" + "=" * 50)
            print("以上数据可供 Claude 分析爆款规律并生成衍生文案")
        return

    # 批量
    if args.batch:
        try:
            lines = [l.strip() for l in open(args.batch, "r", encoding="utf-8") if l.strip()]
        except FileNotFoundError:
            print(f"[ERROR] 文件不存在: {args.batch}", file=sys.stderr)
            sys.exit(1)

        results = []
        for i, line in enumerate(lines, 1):
            print(f"\n{'#' * 50}", file=sys.stderr)
            print(f"# [{i}/{len(lines)}] {line[:50]}", file=sys.stderr)

            if line.startswith("http") or "douyin.com" in line or "v.douyin.com" in line:
                r = research_by_url(line, count=args.count, sort_type=sort_type)
            else:
                r = research_by_keyword(line, count=args.count, sort_type=sort_type)

            results.append(r)

            if not args.json:
                print(f"\n# 第 {i} 组结果:")
                print(r["summary"])

            time.sleep(1)

        if args.json:
            print(json.dumps({"ok": True, "count": len(results), "results": results}, ensure_ascii=False, indent=2))

        print(f"\n批量完成: {len(results)} 组", file=sys.stderr)


if __name__ == "__main__":
    main()
