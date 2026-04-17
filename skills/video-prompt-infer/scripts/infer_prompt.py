#!/usr/bin/env python3
"""视频二创提示词推断 — 转写原视频和二创视频，输出格式化对比文本。

用法:
  python infer_prompt.py --original "原视频URL" --derivative "二创URL"
  python infer_prompt.py --original "分享口令..." --derivative "分享口令..."
  python infer_prompt.py --batch pairs.txt
"""

from __future__ import annotations

import json
import os
import sys

# 复用 video-to-text 的转写能力
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_VTT_DIR = os.path.join(os.path.dirname(_SCRIPT_DIR), "..", "video-to-text", "scripts")
sys.path.insert(0, _VTT_DIR)

from url_to_text import url_to_text  # noqa: E402


def _format_transcript(result: dict, label: str) -> str:
    """格式化单条转写结果。"""
    if not result.get("ok"):
        return f"【{label}】\n转写失败: {result.get('error', '未知错误')}\n"

    title = result.get("title", "")
    transcript = result.get("transcript", "")
    lines = [f"【{label}】"]
    if title:
        lines.append(f"标题: {title}")
    lines.append("---")
    lines.append(transcript)
    return "\n".join(lines)


def infer_prompt(original_url: str, derivative_url: str) -> dict:
    """转写两个视频并输出格式化对比文本。

    返回:
      {"ok": True, "text": "格式化对比文本...", "original": {...}, "derivative": {...}}
      {"ok": False, "error": "..."}
    """
    # 转写原视频
    original_result = url_to_text(original_url)

    # 转写二创视频
    derivative_result = url_to_text(derivative_url)

    # 构建格式化输出
    sep = "=" * 40
    parts = [
        _format_transcript(original_result, "原视频文案"),
        "",
        sep,
        "",
        _format_transcript(derivative_result, "二创文案"),
        "",
        sep,
        "",
        "请分析两个视频文案的差异，从以下维度推断二创提示词：",
        "1. 文案改造方式（改写/扩写/缩写/点评/重新组织/混剪文案）",
        "2. 结构调整（开头处理、节奏变化、结尾处理）",
        "3. 语气/风格变化",
        "4. 内容增删（保留了什么、删除了什么、新增了什么）",
        "5. 总结可复用的二创提示词模板",
    ]

    combined_text = "\n".join(parts)

    both_ok = original_result.get("ok", False) and derivative_result.get("ok", False)

    return {
        "ok": both_ok,
        "text": combined_text,
        "original": original_result,
        "derivative": derivative_result,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="视频二创提示词推断")
    parser.add_argument("--original", help="原视频链接或分享口令")
    parser.add_argument("--derivative", help="二创视频链接或分享口令")
    parser.add_argument(
        "--batch",
        help="批量处理文件，每行一组：原视频URL|二创URL",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 格式（默认输出格式化文本）",
    )
    args = parser.parse_args()

    if not args.original and not args.batch:
        parser.error("请提供 --original + --derivative 或 --batch")

    # 单组对比
    if args.original:
        if not args.derivative:
            parser.error("--original 需要 --derivative 配合使用")

        result = infer_prompt(args.original, args.derivative)

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["text"])

        if not result["ok"]:
            print(
                "\n[警告] 部分视频转写失败，请检查上方错误信息",
                file=sys.stderr,
            )

        return

    # 批量处理
    if args.batch:
        try:
            lines = [
                line.strip()
                for line in open(args.batch, "r", encoding="utf-8")
                if line.strip()
            ]
        except FileNotFoundError:
            print(
                json.dumps({"ok": False, "error": f"文件不存在: {args.batch}"}),
            )
            sys.exit(1)

        results = []
        for i, line in enumerate(lines, 1):
            # 支持用 | 或制表符分隔
            sep = "|" if "|" in line else "\t"
            parts = line.split(sep, 1)
            if len(parts) != 2:
                print(
                    f"[{i}] 跳过格式错误的行: {line[:50]}...",
                    file=sys.stderr,
                )
                continue

            orig_url, deriv_url = parts[0].strip(), parts[1].strip()
            print(f"[{i}/{len(lines)}] 对比分析中...", file=sys.stderr)

            result = infer_prompt(orig_url, deriv_url)
            results.append(result)

            if not args.json:
                print(f"\n{'#' * 50}")
                print(f"# 第 {i} 组对比")
                print(f"{'#' * 50}\n")
                print(result["text"])

        if args.json:
            print(
                json.dumps(
                    {"ok": True, "count": len(results), "results": results},
                    ensure_ascii=False,
                    indent=2,
                ),
            )

        success = sum(1 for r in results if r["ok"])
        print(
            f"\n批量完成: {success}/{len(results)} 组成功",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
