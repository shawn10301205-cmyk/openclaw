---
name: content-research
description: >
  多源爆款搜集+AI重组文案技能。输入一个抖音视频链接或分享口令，自动搜索全网相关爆款内容，
  分析共同点（流量密码）和不同点（延伸方向），按每个延伸方向生成独立衍生文案。
  使用场景：(1) 给定一条视频，搜集同类爆款，分析规律，生成多篇衍生二创文案
  (2) 批量分析多个主题的爆款素材，积累二创模式库
  (3) 竞品文案分析，提取可复用的爆款结构和延伸方向
  触发词：搜集爆款、分析爆款、文案重组、爆款分析、多源素材、衍生文案、爆款搜集、内容研究、素材搜集、二创文案、找爆款、爆款规律
  当用户提到"搜集爆款"、"分析爆款"、"找爆款"、"文案重组"、"衍生文案"、"多源素材"、"内容研究"、"素材搜集"时都应触发此技能。
  也适用于用户想分析某个主题下多段视频的共性规律和差异方向、或想基于爆款素材生成新文案的场景。
---

# 多源爆款搜集 + AI 重组文案

给定一条抖音视频（链接或分享口令），自动完成：搜索相关爆款 → 转写文案 → 分析规律 → 生成衍生文案。

## 前置条件

- 完全独立，无需其他技能依赖
- API Key 已内置，开箱即用
- 如需覆盖 TikHub Key，设置环境变量 `TIKHUB_API_KEY`
- 如需覆盖转写 Key，设置环境变量 `TE_92K_KEY`
- 需要 `requests` 库：`pip3 install requests`

## 工作流路由

### 1. 单条爆款分析

**触发**: "帮我搜集这个主题的爆款"、"分析这个视频的相关爆款"、"找同类爆款生成文案"

```bash
# 通过视频链接
python3 skills/content-research/scripts/research_and_write.py \
  --url "https://www.douyin.com/video/xxx"

# 通过分享口令
python3 skills/content-research/scripts/research_and_write.py \
  --url "7.61 Ljc:/ ... https://v.douyin.com/xxx/ 复制此链接..."
```

### 2. 按关键词直接搜索

**触发**: "搜集'女性力量'相关的爆款"、"找'中国女篮'的爆款素材"

```bash
python3 skills/content-research/scripts/research_and_write.py \
  --keyword "女性力量" --count 10
```

### 3. 批量分析

**触发**: "批量分析这几个主题的爆款"、"帮我搜集多组爆款素材"

```bash
# 文件格式：每行一个 URL 或关键词
python3 skills/content-research/scripts/research_and_write.py --batch topics.txt
```

### 4. 指定搜索排序

```bash
# 按最多点赞排序（找最爆的）
python3 skills/content-research/scripts/research_and_write.py \
  --keyword "女警 身材" --count 10 --sort likes

# 按综合排序（默认）
python3 skills/content-research/scripts/research_and_write.py \
  --keyword "女警 身材" --count 10 --sort general
```

## 脚本输出格式

脚本输出 JSON，包含三个部分：

```json
{
  "original": {
    "aweme_id": "xxx",
    "desc": "原视频文案描述",
    "title": "视频标题",
    "transcript": "语音转写文案（如果有口播）",
    "hashtags": ["#女性", "#女警"],
    "keywords_for_search": "提取的搜索关键词"
  },
  "viral_videos": [
    {
      "rank": 1,
      "author": "作者昵称",
      "desc": "爆款文案",
      "transcript": "转写文案（如果有）",
      "likes": 45906,
      "comments": 853,
      "shares": 17001,
      "url": "https://www.douyin.com/video/xxx"
    }
  ],
  "analysis_ready": true,
  "summary": "结构化摘要供 Claude 分析"
}
```

## Claude 分析和文案生成流程

脚本完成数据采集后，Claude 按以下步骤分析和生成：

### 第一步：分析爆款规律

**找共同点（流量密码）：**
- 高频标签和情绪词
- 画面风格和核心情绪
- 结构特点（开头方式、叙事节奏）
- 这些共同点 = 这个赛道的流量密码

**找不同点（延伸方向）：**
- 每个爆款的差异化切入点
- 例如：反差冲击、日常偶遇、怀旧情怀、人物故事、态度金句
- 每个方向 = 一个可延伸的衍生文案方向

### 第二步：生成衍生文案

以原视频核心内容为基底，往每个延伸方向各生成一篇 300-500 字衍生文案。

开头吸引法则（每个方向用不同的开头技巧）：
- **反差冲击**：用一个打破常识的对比开头
- **悬念式**：先抛一个让人好奇的场景
- **情绪共鸣**：唤醒某种集体记忆
- **反问式**：用一个问题直接抓住注意力
- **断言式**：一句话定调，不解释

每篇文案要求：
- 基于原视频核心内容，不是泛泛而谈
- 300-500 字
- 结尾附建议标签和画面建议
- 标注使用的开头法则和延伸方向

### 第三步：输出最终结果

输出结构：

```
## 原视频信息
（文案、标签、核心主题）

## 爆款共同点（流量密码）
1. ...
2. ...

## 爆款不同点（延伸方向）
| 方向 | 爆款来源 | 可借鉴点 |
|------|---------|---------|
| ...  | ...     | ...     |

## 衍生文案

### 方向一：xxx（开头法则：xxx）
（300-500字文案）
**建议标签：** ...
**建议画面：** ...

### 方向二：xxx（开头法则：xxx）
...
```

## 注意事项

- TikHub 搜索每次消耗 API 积分，合理设置 --count（建议 10-20）
- 视频转写每次消耗转写积分，纯画面配乐的视频转写可能为空，此时用 desc 文案代替
- 搜索间隔至少 1 秒，避免触发限流
- 批量分析时注意 API 额度消耗
