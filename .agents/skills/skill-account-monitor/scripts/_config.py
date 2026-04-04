"""公共配置 — API Key 和常量统一管理。"""

import os
from pathlib import Path

# ── TikHub API Key（硬编码，环境变量优先）──────────────
TIKHUB_API_KEY = "nY5bGPI1zQ2bpH6aGKKk6TjqPWrKAYR93xfhrWCvaPWgtFDiES2tc3fDGQ=="

def get_tikhub_api_key() -> str:
    return os.environ.get("TIKHUB_API_KEY", TIKHUB_API_KEY).strip()

# ── 数据目录 ─────────────────────────────────────────
DATA_DIR = Path(os.environ.get("ACCOUNT_MONITOR_DATA_DIR", str(Path.home() / ".account-monitor")))
POOL_FILE = DATA_DIR / "pool.json"
CACHE_DIR = DATA_DIR / "posts-cache"
ALERTS_FILE = DATA_DIR / "alerts.json"
CACHE_KEEP_DAYS = 2  # 缓存保留天数（今天 + 昨天）

# ── TikHub ───────────────────────────────────────────
TIKHUB_BASE_URL = "https://api.tikhub.dev"
PAGE_INTERVAL = 1.0
RATE_LIMIT_RETRIES = (1.0, 2.0, 4.0)

# ── te.92k.fun 语音转写 API ──────────────────────────
TE_92K_API_URL = "https://te.92k.fun/user/analysis"
TE_92K_KEY_BUILTIN = "zyj_cea870128069d6e3a9cce17b504f4dd42"

def get_te92k_key() -> str:
    return os.environ.get("TE_92K_KEY", TE_92K_KEY_BUILTIN).strip()

# ── 请求头 ───────────────────────────────────────────
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.douyin.com/",
}
