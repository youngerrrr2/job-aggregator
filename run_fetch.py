"""抓取 CLI 入口（可手动运行，也供 Windows 任务计划 / UI 按钮调用）。

用法：
    python run_fetch.py                          # 全部启用平台
    python run_fetch.py --platform liepin job51  # 只跑指定平台
    python run_fetch.py --limit-keywords 1       # 每组只试第一个关键词（调试）
    python run_fetch.py --dry-run                # 只打印计划，不联网
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)                       # 任意工作目录下相对路径都成立
sys.path.insert(0, str(ROOT))

from jobaggregator.config import ConfigError, load_config      # noqa: E402
from jobaggregator.paths import LOCK_PATH, LOGS_DIR, ensure_dirs  # noqa: E402
from jobaggregator.pipeline import run_fetch                    # noqa: E402

log = logging.getLogger("jobaggregator")


def setup_logging() -> None:
    """文件始终写；控制台仅在真实终端（pythonw 下 stdout 为 None 时不能碰）。"""
    ensure_dirs()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    fh = logging.FileHandler(LOGS_DIR / f"fetch_{date.today():%Y%m%d}.log",
                             encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    if sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        ch = logging.StreamHandler(stream=sys.stdout)
        ch.setFormatter(fmt)
        log.addHandler(ch)
    log.setLevel(logging.INFO)


def acquire_lock() -> bool:
    """防止任务计划与 UI 按钮同时抓取；已有锁则返回 False。"""
    if LOCK_PATH.exists():
        try:
            pid = int(LOCK_PATH.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)  # 进程还活着 → 抛异常即未活
            return False
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            pass  # 锁文件残留（进程已死）→ 覆盖
        except Exception:
            return False
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
    return True


def release_lock() -> None:
    try:
        LOCK_PATH.unlink()
    except FileNotFoundError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="财务岗位聚合抓取")
    parser.add_argument("--platform", nargs="*", default=None,
                        help="只跑指定平台（如 liepin job51）")
    parser.add_argument("--limit-keywords", type=int, default=None,
                        help="每组只取前 N 个关键词（调试用）")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划不联网")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    args = parser.parse_args()

    setup_logging()
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        log.error("配置错误：%s", e)
        return 2

    if not args.dry_run:
        if not acquire_lock():
            log.warning("已有抓取任务进行中（%s 存在），本次退出", LOCK_PATH)
            return 1
    try:
        ok = run_fetch(cfg,
                       only_platforms=set(args.platform) if args.platform else None,
                       limit_keywords=args.limit_keywords,
                       dry_run=args.dry_run)
    finally:
        if not args.dry_run:
            release_lock()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
