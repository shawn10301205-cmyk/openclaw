---
name: skill-account-monitor
description: >
  抖音账号池监控技能 — 对标账号自动监控新发作品、爆款预警、历史高赞筛选、文案洗稿改写。
  使用场景：(1) 添加/移除/列出抖音对标账号 (2) 定时每小时监控所有账号新发作品
  (3) 1小时破万赞爆款实时告警 (4) 按时间筛选历史10万+爆款
  (5) 获取视频文案+高赞评论并自动改写/润色。
  触发词：监控账号、添加账号、对标账号、爆款预警、洗稿、改写文案、高赞作品、账号池、抖音监控
---

# 抖音账号池监控

## 前置条件

TikHub API Key 已内置，开箱即用。如需覆盖，设置环境变量 `TIKHUB_API_KEY`。

脚本目录: `.agents/skills/skill-account-monitor/scripts/`
数据目录: `~/.account-monitor/`（自动创建）

## 工作流路由

根据用户意图，路由到对应操作：

### 1. 管理账号池（添加/移除/列出）

**触发**: "添加监控账号 @xxx"、"把张三加到监控"、"列出所有账号"、"移除张三"

```bash
# 添加（通过 URL 或 sec_user_id）
python3 .agents/skills/skill-account-monitor/scripts/manage_pool.py add --url "https://www.douyin.com/user/MS4wLjAB..."

# 添加（通过 sec_user_id）
python3 .agents/skills/skill-account-monitor/scripts/manage_pool.py add --sec-user-id "MS4wLjAB..."

# 移除
python3 .agents/skills/skill-account-monitor/scripts/manage_pool.py remove --nickname "张三"

# 列出
python3 .agents/skills/skill-account-monitor/scripts/manage_pool.py list

# 刷新所有账号资料
python3 .agents/skills/skill-account-monitor/scripts/manage_pool.py sync-profiles

# 查看数量
python3 .agents/skills/skill-account-monitor/scripts/manage_pool.py count
```

添加账号后自动拉取昵称、粉丝数等资料，同时初始化最新视频 ID 作为增量基线。后续监控只抓取比基线更新的作品。

### 2. 定时监控新发作品

**触发**: "开始每小时监控"、"监控所有账号"、"定时检查新作品"

**步骤**:

1. 执行增量监控（自动根据 last_aweme_id 断点只抓新帖）:

```bash
python3 .agents/skills/skill-account-monitor/scripts/monitor_new_posts.py
```

2. 执行爆款检测:

```bash
python3 .agents/skills/skill-account-monitor/scripts/check_viral.py
```

3. 汇报账号池整体情况:

```bash
python3 .agents/skills/skill-account-monitor/scripts/manage_pool.py list
python3 .agents/skills/skill-account-monitor/scripts/manage_pool.py count
```

4. 设置 CronCreate 定时任务（每 57 分钟执行一次增量监控）:

```
CronCreate: cron "57 * * * *", prompt "运行账号池监控：执行 python3 .agents/skills/skill-account-monitor/scripts/monitor_new_posts.py，然后执行 python3 .agents/skills/skill-account-monitor/scripts/check_viral.py 检查爆款，最后执行 python3 .agents/skills/skill-account-monitor/scripts/manage_pool.py list 查看账号池状态。汇报：新作品数量、爆款情况、账号池整体状态（总账号数、各账号最近同步时间）。"
```

**监控完成后必须汇报以下内容：**

- 📊 检查了 X 个账号，发现 Y 条新作品
- 🔥 爆款情况（有则列出，无则说明）
- 👥 账号池状态：总账号数、各账号昵称、粉丝数、最近同步时间

### 3. 爆款检测与告警

**触发**: "检查爆款"、"有没有爆款"、"破万赞的"

```bash
# 默认：最近1小时、1万赞
python3 .agents/skills/skill-account-monitor/scripts/check_viral.py

# 自定义：最近2小时、5万赞
python3 .agents/skills/skill-account-monitor/scripts/check_viral.py --hours 2 --min-likes 50000

# 不限时间，只看点赞数
python3 .agents/skills/skill-account-monitor/scripts/check_viral.py --all --min-likes 100000
```

检测到爆款时，以醒目格式报告给用户：

- 作者 + 标题
- 点赞/评论/收藏数据
- 发布时间
- 视频链接

### 4. 历史高赞筛选

**触发**: "查看张三最近30天的10万+爆款"、"历史高赞作品"、"拉取历史数据"

```bash
# 指定账号 + 时间 + 点赞阈值
python3 .agents/skills/skill-account-monitor/scripts/fetch_history.py --account "张三" --days 30 --min-likes 100000

# 所有账号
python3 .agents/skills/skill-account-monitor/scripts/fetch_history.py --all-accounts --days 7 --min-likes 50000
```

输出表格格式呈现：序号 | 作者 | 标题 | 点赞 | 评论 | 发布时间 | 链接

### 5. 文案洗稿/改写

**触发**: "洗稿"、"改写这个视频的文案"、"润色文案"、"写口播稿"、"模仿爆款"

**步骤**:

1. 获取视频文案和评论（优先使用 te.92k.fun 语音转写，自动降级到 TikHub）:

```bash
# 通过视频链接（支持分享口令格式）
python3 .agents/skills/skill-account-monitor/scripts/get_transcript.py --url "https://www.douyin.com/video/xxx"

# 通过分享口令（直接粘贴抖音分享内容）
python3 .agents/skills/skill-account-monitor/scripts/get_transcript.py --url "1.51 g@b.nd 07/16 VLJ:/ ...  https://v.douyin.com/xxx/ 复制此链接..."

# 通过 aweme_id
python3 .agents/skills/skill-account-monitor/scripts/get_transcript.py --aweme-id "7xxxxxxxxx"

# 从缓存中按账号取
python3 .agents/skills/skill-account-monitor/scripts/get_transcript.py --account "张三" --index 0

# 强制使用 TikHub（不走 92k 语音转写）
python3 .agents/skills/skill-account-monitor/scripts/get_transcript.py --url "..." --force-tikhub
```

输出 JSON 中 `transcript` 为语音转写文案（完整口播内容），`transcript_source` 标注来源（`92k` 或 `tikhub`）。

2. 读取 `references/rewrite_prompts.md` 选择改写模板:
   - `oral_rewrite` — 口播稿改写
   - `viral_imitate` — 爆款模仿
   - `graphic_rewrite` — 图文改写（小红书/公众号）
   - `polish` — 片段润色

3. 根据用户选择的模板，使用 Claude 自身 AI 直接生成改写文案。
   将原文案 + 高赞评论 + 改写模板组合为 prompt，直接输出改写结果。

4. 如需多版本，循环生成 2-3 个不同版本供用户选择。

## 注意事项

- 所有脚本输出最后一段为 JSON，前面是人类可读文本。解析结果时读取 JSON 部分。
- TikHub API 有速率限制，脚本已内置重试逻辑（429 重试 3 次）。
- 账号间请求间隔 1 秒，33 个账号约 33 秒完成一轮。
- 数据存储在 `~/.account-monitor/`，纯文件存储，无需数据库。
- **缓存按天分文件**：`posts-cache/<account>/2026-04-03.json`，自动清理 2 天前数据，防止磁盘膨胀。
- **添加账号自动初始化**：添加时自动抓取最新视频 ID 作为基线，无需手动 `--all-pages`。
- 首次使用建议先 `manage_pool.py sync-profiles` 刷新所有账号资料。
- 若缺少依赖，运行 `pip3 install requests`。
