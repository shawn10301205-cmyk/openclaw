# TikHub API 速查

## 认证

所有请求 Header 添加: `Authorization: Bearer {TIKHUB_API_KEY}`

## 常用端点

### 用户作品列表（APP 接口，优先）

```
GET /api/v1/douyin/app/v3/fetch_user_post_videos
参数: sec_user_id, max_cursor (int), count (默认20)
返回: { code, data: { aweme_list, has_more, max_cursor } }
```

### 用户作品列表（WEB 接口，备用）

```
GET /api/v1/douyin/web/fetch_user_post_videos
参数: sec_user_id, max_cursor (str), count, filter_type=0
```

### 视频详情

```
GET /api/v1/douyin/web/fetch_video_info
参数: aweme_id
返回: { code, data: { aweme_detail: { desc, statistics, author, video, ... } } }
```

### 视频评论

```
GET /api/v1/douyin/web/fetch_video_comments
参数: aweme_id, cursor (int), count (默认20)
返回: { code, data: { comments: [{ text, digg_count, user: { nickname } }] } }
```

### 用户资料

```
GET /api/v1/douyin/web/fetch_user_profile
参数: sec_user_id
返回: { code, data: { user: { nickname, follower_count, ... } } }
```

## 限流与重试

- 429 状态码 = 限流，等待后重试
- 推荐重试间隔: 1s → 2s → 4s
- 翻页间隔至少 1 秒
- 33 个账号一轮约 33 秒

## 数据结构

### aweme（作品）字段

| 字段                     | 说明                    |
| ------------------------ | ----------------------- |
| aweme_id                 | 作品唯一 ID             |
| desc                     | 文案/描述               |
| create_time              | 发布时间（Unix 时间戳） |
| share_url                | 分享链接                |
| statistics.digg_count    | 点赞数                  |
| statistics.comment_count | 评论数                  |
| statistics.collect_count | 收藏数                  |
| statistics.share_count   | 转发数                  |
| author.nickname          | 作者昵称                |
| video.cover              | 封面图                  |

### sec_user_id 提取

从抖音主页 URL 提取: `/user/(MS4wLjAB[\w\-]+)`
格式示例: `MS4wLjABAAAAxxxxxxxxxxxxxxxxxx`
