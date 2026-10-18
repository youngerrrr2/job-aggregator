"""项目内统一路径常量（按本文件定位，与工作目录无关）。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
CAPTURES_DIR = DATA_DIR / "captures"
COOKIES_DIR = DATA_DIR / "cookies"
BROWSER_PROFILE_DIR = DATA_DIR / "browser_profile"
DB_PATH = DATA_DIR / "jobs.db"
LOCK_PATH = DATA_DIR / "fetch.lock"


def ensure_dirs() -> None:
    for d in (DATA_DIR, LOGS_DIR, COOKIES_DIR, CAPTURES_DIR):
        d.mkdir(parents=True, exist_ok=True)
