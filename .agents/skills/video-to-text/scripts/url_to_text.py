#!/usr/bin/env python3
"""视频 URL 转文本 — 通过 te.92k.fun 将抖音视频链接/分享口令转为语音转写文案。

用法:
  python url_to_text.py --url "https://www.douyin.com/video/xxx"
  python url_to_text.py --url "1.51 g@b.nd ... https://v.douyin.com/xxx/ 复制此链接..."
  python url_to_text.py --url "..." --text-only
  python url_to_text.py --batch urls.txt
"""

from __future__ import annotations

import json
import os
import sys

import requests

# ── 配置 ─────────────────────────────────────────────

API_URL = "https://te.92k.fun/user/analysis"
API_KEY = os.environ.get("TE_92K_KEY", "zyj_cea870128069d6e3a9cce17b504f4dd42").strip()


# ── 核心函数 ──────────────────────────────────────────

def url_to_text(url: str) -> dict:
    """将视频 URL/分享口令转为文本。

    返回:
      {"ok": True, "transcript": "...", "title": "...", "source": "92k", "remaining_points": N}
      {"ok": False, "error": "..."}
    """
    try:
        resp = requests.post(
            API_URL,
            json={"key": API_KEY, "url": url},
            headers={"Content-Type": "application/json"},
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()

        if payload.get("code") != 200:
            return {"ok": False, "error": payload.get("msg") or str(payload)}

        # 提取转写文案
        transcripts = payload.get("transcripts") or []
        transcript_text = ""
        if transcripts and isinstance(transcripts, list):
            transcript_text = transcripts[0].get("text", "")

        # 提取视频信息
        video = payload.get("video") or {}
        title = video.get("title", "")

        if not transcript_text and video.get("text"):
            transcript_text = video["text"]

        if not transcript_text:
            return {"ok": False, "error": "API 返回空文案，可能视频无语音"}

        # 积分信息
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
        return {"ok": False, "error": "请求超时（60秒），视频可能过长"}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"网络错误: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"未知错误: {e}"}


# ── CLI ───────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="视频 URL 转文本")
    parser.add_argument("--url", help="视频链接或分享口令")
    parser.add_argument("--batch", help="批量处理，每行一个 URL 的文件路径")
    parser.add_argument("--text-only", action="store_true", help="只输出纯文本，不输出 JSON")
    args = parser.parse_args()

    if not args.url and not args.batch:
        parser.error("请提供 --url 或 --batch")

    # 单个 URL
    if args.url:
        result = url_to_text(args.url)
        if args.text_only:
            if result["ok"]:
                print(result["transcript"])
            else:
                print(f"[ERROR] {result['error']}", file=sys.stderr)
                sys.exit(1)
        else:
            # 人类可读 + JSON
            if result["ok"]:
                print(f"=== 视频文案 ===")
                print(result["transcript"])
                if result.get("title"):
                    print(f"\n标题: {result['title']}")
                print(f"剩余积分: {result.get('remaining_points', '?')}")
            else:
                print(f"[ERROR] {result['error']}", file=sys.stderr)
            print("\n" + json.dumps(result, ensure_ascii=False, indent=2))
        return

    # 批量处理
    if args.batch:
        try:
            urls = [line.strip() for line in open(args.batch, "r", encoding="utf-8") if line.strip()]
        except FileNotFoundError:
            print(json.dumps({"ok": False, "error": f"文件不存在: {args.batch}"}, ensure_ascii=False))
            sys.exit(1)

        results = []
        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}] 转写中...", file=sys.stderr)
            result = url_to_text(url)
            result["input_url"] = url
            results.append(result)

            if args.text_only and result["ok"]:
                print(f"--- 第 {i} 条 ---")
                print(result["transcript"])
                print()

        if not args.text_only:
            print(json.dumps({"ok": True, "count": len(results), "results": results}, ensure_ascii=False, indent=2))

        success = sum(1 for r in results if r["ok"])
        print(f"\n批量完成: {success}/{len(results)} 成功", file=sys.stderr)


if __name__ == "__main__":
    main()
