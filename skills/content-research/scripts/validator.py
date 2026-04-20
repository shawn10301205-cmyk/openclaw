#!/usr/bin/env python3
"""Content-research 输出校验器。

对 LLM 生成的改写文案做三件事：
1. 字数审查：去标点后统计纯文字字数，必须 500–800
2. 红线审查：扫描敏感词 / 人身攻击词 / 政治相关词
3. 流程审查：检查输出是否包含所有必做步骤

用法:
  # 校验单个文案文件
  python validator.py --file output.md

  # 从 stdin 读取
  python validator.py --stdin < output.md

  # 只校验字数（传入文案文本）
  python validator.py --count-only "文案内容..."

  # 严格模式：任一检查失败则 exit 1
  python validator.py --file output.md --strict
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ── 配置 ─────────────────────────────────────────────

MIN_WORDS = 450
MAX_WORDS = 800

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILL_DIR = Path(__file__).resolve().parent.parent

# ── 敏感词库 ─────────────────────────────────────────

# 人身攻击 / 主观定性词汇
ATTACK_WORDS = [
    "嚣张", "无耻", "泼妇", "人渣", "贱人", "垃圾", "废物",
    "不要脸", "死不要脸", "恶心", "下贱", "贱货", "烂人",
    "绿茶婊", "白莲花", "心机婊", "渣男", "渣女",
    "废物点心", "脑子有病", "神经病", "疯子",
    "畜生", "禽兽", "狗东西", "猪狗不如",
]

# 涉政 / 涉军 / 涉警 敏感词
POLITICAL_WORDS = [
    "政府", "官方", "政策", "相关部门", "有关部门",
    "懒政", "不作为", "腐败", "贪污",
    "武警", "军队", "解放军", "公安",
    "反党", "反政府", "反华",
]

# 民族 / 宗教 敏感简称（应使用全称）
ETHNIC_SHORTHAND = [
    "回回", "蛮子", "蒙族", "维族", "鲜族",
    "蒙古大夫", "蒙古人", "突厥族", "突厥人",
    "黑非洲", "伊斯兰原教旨主义",
    "北朝鲜", "前苏联",
]

# 港澳台 敏感表述
TERRITORY_WRONG = [
    "中港台", "台湾政府", "香港总统", "台湾总统",
    "港澳台明星",
]

# 灾难消费词汇
DISASTER_SENSITIVE = [
    "活该", "报应", "自找的", "罪有应得", "死得好",
]


# ── 字数统计 ─────────────────────────────────────────

# 中英文标点 + markdown 标记
_PUNCT_RE = re.compile(
    r'[，。！？、；：\u201c\u201d\u2018\u2019\uff08\uff09\u3010\u3011\u300a\u300b\u2026\u2014\u00b7\s'
    r'!\?\.,;:\'"()\[\]{}<>/\\@#\$%\^&\*\+=\|~`_-]'
    r'|[\U0001F600-\U0001F64F]'  # emoji
)


def count_words(text: str) -> int:
    """去掉标点、emoji、markdown 标记后统计纯文字字数。"""
    # 去掉 markdown 加粗/斜体标记
    clean = re.sub(r'\*+', '', text)
    # 去掉 markdown 链接
    clean = re.sub(r'\[.*?\]\(.*?\)', '', clean)
    # 去掉 markdown 标题标记
    clean = re.sub(r'^#{1,6}\s*', '', clean, flags=re.MULTILINE)
    # 去掉标点和空白
    clean = _PUNCT_RE.sub('', clean)
    return len(clean)


# ── 红线扫描 ─────────────────────────────────────────

def scan_redlines(text: str) -> list[dict]:
    """扫描文案中的红线违规，返回 [{rule, word, context}]。"""
    hits: list[dict] = []

    # 人身攻击
    for w in ATTACK_WORDS:
        if w in text:
            hits.append({"rule": "人身攻击", "word": w, "context": _extract_context(text, w)})

    # 涉政
    for w in POLITICAL_WORDS:
        if w in text:
            hits.append({"rule": "涉政敏感", "word": w, "context": _extract_context(text, w)})

    # 民族宗教
    for w in ETHNIC_SHORTHAND:
        if w in text:
            hits.append({"rule": "民族宗教不当简称", "word": w, "context": _extract_context(text, w)})

    # 领土
    for w in TERRITORY_WRONG:
        if w in text:
            hits.append({"rule": "港澳台领土表述", "word": w, "context": _extract_context(text, w)})

    # 灾难消费
    for w in DISASTER_SENSITIVE:
        if w in text:
            hits.append({"rule": "灾难消费", "word": w, "context": _extract_context(text, w)})

    return hits


def _extract_context(text: str, word: str, radius: int = 15) -> str:
    """提取命中词周围的上下文。"""
    idx = text.find(word)
    if idx == -1:
        return word
    start = max(0, idx - radius)
    end = min(len(text), idx + len(word) + radius)
    return text[start:end]


# ── 流程完整性检查 ───────────────────────────────────

# 必须出现的章节标题（正则匹配，模糊匹配即可）
REQUIRED_SECTIONS = [
    ("原视频信息", r"原视频信息"),
    ("原文拆解", r"原文拆解"),
    ("爆款机制提取", r"爆款机制"),
    ("改写机制", r"选用的改写机制|改写机制"),
    ("阶段一复刻稿", r"阶段一|复刻稿"),
    ("阶段二轻度改写", r"阶段二|轻度改写"),
    ("阶段三深度改写", r"阶段三|深度改写"),
]

# 每个阶段内必须包含的要素
STAGE_ELEMENTS = {
    "stage1": [
        ("钩子保留", r"钩子.*保留"),
        ("主体完整", r"主体.*完整"),
    ],
    "stage2": [
        ("爆款机制", r"爆款机制"),
        ("素材来源", r"素材来源|素材.*原视频"),
    ],
    "stage3": [
        ("爆款机制", r"爆款机制"),
        ("素材来源", r"素材来源|素材.*原视频"),
        ("建议标签", r"建议标签"),
        ("建议画面", r"建议画面"),
    ],
}


def find_stages(text: str) -> dict[str, tuple[int, int]]:
    """定位三个阶段的文本范围。返回 {stage: (start, end)}。"""
    stages: dict[str, tuple[int, int]] = {}
    markers = [
        ("stage1", r"阶段一|复刻稿"),
        ("stage2", r"阶段二|轻度改写"),
        ("stage3", r"阶段三|深度改写"),
    ]
    positions = []
    for name, pattern in markers:
        m = re.search(pattern, text)
        if m:
            positions.append((name, m.start()))

    # 按 position 排序后确定范围
    positions.sort(key=lambda x: x[1])
    for i, (name, pos) in enumerate(positions):
        end = positions[i + 1][1] if i + 1 < len(positions) else len(text)
        stages[name] = (pos, end)

    return stages


def check_workflow(text: str) -> dict:
    """检查流程完整性。返回 {sections: [...], missing: [...], stage_checks: {...}}。"""
    found = []
    missing = []

    for name, pattern in REQUIRED_SECTIONS:
        if re.search(pattern, text):
            found.append(name)
        else:
            missing.append(name)

    # 检查各阶段要素
    stages = find_stages(text)
    stage_checks: dict[str, dict] = {}
    for stage_key, elements in STAGE_ELEMENTS.items():
        if stage_key not in stages:
            stage_checks[stage_key] = {"status": "MISSING", "elements": []}
            continue

        start, end = stages[stage_key]
        stage_text = text[start:end]
        el_results = []
        for el_name, el_pattern in elements:
            el_results.append({
                "name": el_name,
                "found": bool(re.search(el_pattern, stage_text)),
            })
        all_found = all(e["found"] for e in el_results)
        stage_checks[stage_key] = {
            "status": "PASS" if all_found else "INCOMPLETE",
            "elements": el_results,
        }

    return {
        "sections_found": found,
        "sections_missing": missing,
        "stages": stage_checks,
    }


# ── 改写文案提取 ────────────────────────────────────

def extract_rewrites(text: str) -> dict[str, str]:
    """从输出中提取三篇改写文案的文本。"""
    stages = find_stages(text)
    rewrites: dict[str, str] = {}

    for stage_key, (start, end) in stages.items():
        stage_text = text[start:end]
        # 去掉末尾的 Validator/检查标记行，只保留文案正文
        lines = stage_text.split("\n")
        body_lines = []
        in_validator = False
        for line in lines:
            stripped = line.strip()
            if re.match(r"\*\*(Validator|复刻检查|素材来源|红线审查)", stripped):
                in_validator = True
            if not in_validator and stripped and not stripped.startswith("#"):
                body_lines.append(stripped)
        rewrites[stage_key] = " ".join(body_lines)

    return rewrites


# ── 整体校验 ─────────────────────────────────────────

def validate(text: str) -> dict:
    """运行全部校验，返回完整报告。"""
    rewrites = extract_rewrites(text)

    # 1. 字数审查
    word_results = {}
    for stage, content in rewrites.items():
        wc = count_words(content)
        word_results[stage] = {
            "count": wc,
            "pass": MIN_WORDS <= wc <= MAX_WORDS,
            "min": MIN_WORDS,
            "max": MAX_WORDS,
        }

    # 2. 红线审查（对每篇改写 + 整体）
    redline_results = {}
    for stage, content in rewrites.items():
        hits = scan_redlines(content)
        redline_results[stage] = {
            "pass": len(hits) == 0,
            "hits": hits,
        }

    # 3. 流程审查
    workflow = check_workflow(text)

    # 汇总
    all_word_pass = all(r["pass"] for r in word_results.values())
    all_redline_pass = all(r["pass"] for r in redline_results.values())
    all_workflow_pass = len(workflow["sections_missing"]) == 0 and all(
        s["status"] == "PASS" for s in workflow["stages"].values()
    )

    overall_pass = all_word_pass and all_redline_pass and all_workflow_pass

    return {
        "pass": overall_pass,
        "word_count": word_results,
        "redlines": redline_results,
        "workflow": workflow,
    }


def format_report(report: dict) -> str:
    """将校验报告格式化为可读文本。"""
    lines = []
    status_icon = lambda p: "✅" if p else "❌"
    lines.append("=" * 50)
    lines.append(f"校验结果: {status_icon(report['pass'])} {'全部通过' if report['pass'] else '存在不通过项'}")
    lines.append("=" * 50)

    # 字数
    lines.append("")
    lines.append("【字数审查】")
    stage_names = {"stage1": "阶段一（复刻稿）", "stage2": "阶段二（轻度改写）", "stage3": "阶段三（深度改写）"}
    for stage, info in report["word_count"].items():
        name = stage_names.get(stage, stage)
        icon = status_icon(info["pass"])
        label = "合格" if info["pass"] else (
            f"不足，需扩写至 {info['min']}" if info["count"] < info["min"]
            else f"超标，需精简至 {info['max']}"
        )
        lines.append(f"  {icon} {name}: {info['count']} 字 ({label})")

    # 红线
    lines.append("")
    lines.append("【红线审查】")
    for stage, info in report["redlines"].items():
        name = stage_names.get(stage, stage)
        icon = status_icon(info["pass"])
        if info["pass"]:
            lines.append(f"  {icon} {name}: 通过")
        else:
            lines.append(f"  {icon} {name}: 发现 {len(info['hits'])} 处违规")
            for hit in info["hits"]:
                lines.append(f"      [{hit['rule']}] \"{hit['word']}\" → ...{hit['context']}...")

    # 流程
    lines.append("")
    lines.append("【流程审查】")
    wf = report["workflow"]
    if wf["sections_missing"]:
        lines.append(f"  ❌ 缺失章节: {', '.join(wf['sections_missing'])}")
    else:
        lines.append(f"  ✅ 必要章节齐全 ({len(wf['sections_found'])}/{len(wf['sections_found']) + len(wf['sections_missing'])})")

    for stage_key, stage_info in wf["stages"].items():
        name = stage_names.get(stage_key, stage_key)
        icon = status_icon(stage_info["status"] == "PASS")
        if stage_info["status"] == "MISSING":
            lines.append(f"  {icon} {name}: 未找到")
            continue
        missing_els = [e["name"] for e in stage_info["elements"] if not e["found"]]
        if missing_els:
            lines.append(f"  {icon} {name}: 缺少 {', '.join(missing_els)}")
        else:
            lines.append(f"  {icon} {name}: 要素齐全")

    lines.append("")
    lines.append("=" * 50)
    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Content-research 输出校验器")
    parser.add_argument("--file", "-f", help="待校验的文案文件路径")
    parser.add_argument("--stdin", action="store_true", help="从 stdin 读取文案")
    parser.add_argument("--count-only", "-c", help="只统计字数（传入文案文本）")
    parser.add_argument("--text", "-t", help="直接传入文案文本校验")
    parser.add_argument("--strict", action="store_true", help="严格模式：任一不通过则 exit 1")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式报告")
    args = parser.parse_args()

    # 只统计字数
    if args.count_only:
        wc = count_words(args.count_only)
        in_range = MIN_WORDS <= wc <= MAX_WORDS
        print(f"字数: {wc} ({'合格' if in_range else '不合格，需 500-800'})")
        if args.strict and not in_range:
            sys.exit(1)
        return

    # 获取文案文本
    text = ""
    if args.file:
        try:
            text = Path(args.file).read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"[ERROR] 文件不存在: {args.file}", file=sys.stderr)
            sys.exit(1)
    elif args.text:
        text = args.text
    elif args.stdin:
        text = sys.stdin.read()
    else:
        parser.error("请提供 --file、--text 或 --stdin")

    if not text.strip():
        print("[ERROR] 文案内容为空", file=sys.stderr)
        sys.exit(1)

    report = validate(text)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_report(report))

    if args.strict and not report["pass"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
