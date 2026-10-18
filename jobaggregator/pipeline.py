"""抓取编排：逐平台 → 逐关键词组 → 逐关键词 → 入库 → fetch_runs 记录。

平台之间完全隔离：任何一个平台抛错/登录失效，只记日志与状态，不影响其他平台。
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime

from .browser import BrowserEngine
from .config import AppConfig
from .db import Database, now
from .errors import AuthExpiredError
from .registry import load_all

log = logging.getLogger(__name__)


def _sleep_between_keywords(cfg: AppConfig) -> None:
    lo, hi = cfg.fetch.request_interval_sec
    time.sleep(random.uniform(lo, hi))


def run_fetch(cfg: AppConfig, only_platforms: set[str] | None = None,
              limit_keywords: int | None = None,
              dry_run: bool = False) -> bool:
    """执行一轮抓取。返回是否有平台成功（False = 全军覆没，退出码 1）。"""
    db = Database()
    scraper_classes = load_all()

    enabled = {n: p for n, p in cfg.platforms.items() if p.enabled}
    if only_platforms:
        enabled = {n: p for n, p in enabled.items() if n in only_platforms}
    if not enabled:
        log.error("没有启用的平台")
        return False

    if dry_run:
        log.info("[dry-run] 城市=%s 平台=%s", cfg.city, sorted(enabled))
        for g in cfg.keyword_groups:
            kws = g.keywords[:limit_keywords] if limit_keywords else g.keywords
            log.info("[dry-run] 关键词组 %s（%s）：%s", g.name, g.job_type, "、".join(kws))
        missing = [n for n in enabled if n not in scraper_classes]
        if missing:
            log.info("[dry-run] 尚未实现的平台（将跳过）：%s", "、".join(missing))
        log.info("[dry-run] 数据库：%s（jobs/fetch_runs 两表已就绪）", db.path)
        db.close()
        return True

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    any_ok = False
    engine = BrowserEngine(headless=cfg.fetch.headless)
    try:
        for name, pset in enabled.items():
            cls = scraper_classes.get(name)
            if cls is None:
                log.warning("平台 %s 尚无抓取器，跳过", name)
                continue
            scraper = cls(pset, cfg.fetch)
            seen_keys: set[str] = set()
            platform_dead = False
            t_start = now()
            try:
                scraper.start(engine)
            except Exception as e:
                log.error("[%s] 启动失败：%r", name, e)
                db.record_run(run_id, name, "", "", "error", error_text=repr(e),
                              started_at=t_start)
                continue
            try:
                for group in cfg.keyword_groups:
                    if platform_dead:
                        break
                    kws = group.keywords[:limit_keywords] if limit_keywords else group.keywords
                    for kw in kws:
                        t0 = now()
                        try:
                            items = list(scraper.search(kw, cfg.city))
                        except AuthExpiredError as e:
                            log.warning("[%s] 登录态失效：%s（跳过该平台剩余关键词）",
                                        name, e)
                            db.record_run(run_id, name, group.name, kw,
                                          "auth_failed", error_text=str(e),
                                          started_at=t0)
                            platform_dead = True
                            any_ok = any_ok or False
                            break
                        except Exception as e:
                            log.error("[%s] 关键词「%s」抓取失败：%r", name, kw, e)
                            db.record_run(run_id, name, group.name, kw, "error",
                                          error_text=repr(e), started_at=t0)
                            continue
                        new, upd = db.upsert_jobs(items, group.name, group.job_type)
                        seen_keys.update(it.dedup_key for it in items)
                        status = "ok" if items else "empty"
                        db.record_run(run_id, name, group.name, kw, status,
                                      items_new=new, items_updated=upd,
                                      items_total=len(items), started_at=t0)
                        log.info("[%s] %s / %s：%d 条（新 %d，更新 %d）",
                                 name, group.name, kw, len(items), new, upd)
                        any_ok = True
                        _sleep_between_keywords(cfg)
                archived = db.mark_misses(name, seen_keys,
                                          cfg.fetch.archive_after_misses)
                if archived:
                    log.info("[%s] 本轮归档 %d 条（连续 %d 轮未出现）",
                             name, archived, cfg.fetch.archive_after_misses)
            finally:
                scraper.finish()
    finally:
        engine.close()
        db.close()
    return any_ok
