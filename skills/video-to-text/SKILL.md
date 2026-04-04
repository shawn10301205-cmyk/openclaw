---
name: video-to-text
description: >
  抖音/短视频 URL 转文本技能 — 输入视频链接或分享口令，输出语音转写文案。
  使用场景：(1) 粘贴抖音分享口令获取完整口播文案 (2) 输入视频URL提取语音文字
  (3) 批量转写多个视频。
  触发词：转文字、提取文案、视频转文本、口播稿、语音转写、URL转文本
---

# 视频 URL 转文本

将抖音视频链接或分享口令转换为完整的语音转写文案。

## 前置条件

- API Key 已内置，开箱即用
- 如需覆盖，设置环境变量 `TE_92K_KEY`
- 需要 `requests` 库：`pip3 install requests`

## 工作流路由

### 1. 单个视频转文本

**触发**: "帮我把这个视频转文字"、"提取这个视频的文案"、"转写这个链接"

```bash
# 通过视频链接
python3 skills/video-to-text/scripts/url_to_text.py --url "https://www.douyin.com/video/xxx"

# 通过分享口令（直接粘贴抖音分享内容）
python3 skills/video-to-text/scripts/url_to_text.py --url "1.51 g@b.nd 07/16 VLJ:/ ... https://v.douyin.com/xxx/ 复制此链接..."

# 只输出纯文本（不含 JSON）
python3 skills/video-to-text/scripts/url_to_text.py --url "..." --text-only
```

### 2. 批量转写

**触发**: "把这几个视频都转成文字"

```bash
# 多个链接用换行分隔，写入文件后批量处理
python3 skills/video-to-text/scripts/url_to_text.py --batch urls.txt
```

## 输出格式

```json
{
  "ok": true,
  "transcript": "完整的语音转写文案...",
  "title": "视频标题",
  "source": "92k",
  "remaining_points": 9999
}
```

## 注意事项

- 支持抖音分享口令（包含中文和链接的混合文本）
- 支持抖音标准链接、短链接
- API 积分有限（当前 10000），每次调用消耗积分
- 超时设置 60 秒，适应长视频转写
