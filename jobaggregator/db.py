"""SQLite 存储：建表、upsert 去重、miss 归档、抓取运行记录、UI 查询。

WAL + busy_timeout：抓取进程写、Streamlit 读可并行。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .models import JobItem
from .paths import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    dedup_key        TEXT PRIMARY KEY,
    platform         TEXT NOT NULL,
    site_job_id      TEXT NOT NULL,
    title            TEXT NOT NULL,
    company          TEXT DEFAULT '',
    city             TEXT DEFAULT '',
    district         TEXT DEFAULT '',
    salary_text      TEXT DEFAULT '',
    salary_min_k     REAL,
    salary_max_k     REAL,
    salary_months    INTEGER,
    experience       TEXT DEFAULT '',
    education        TEXT DEFAULT '',
    company_industry TEXT DEFAULT '',
    company_size     TEXT DEFAULT '',
    hr_name          TEXT DEFAULT '',
    tags             TEXT DEFAULT '[]',
    url              TEXT NOT NULL,
    publish_time_text TEXT DEFAULT '',
    keyword_group    TEXT DEFAULT '',
    job_type         TEXT DEFAULT '全职',
    first_seen_at    TEXT NOT NULL,
    last_seen_at     TEXT NOT NULL,
    last_status      TEXT DEFAULT 'active',   -- active | archived
    miss_count       INTEGER DEFAULT 0,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON jobs(last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_platform_status ON jobs(platform, last_status);
CREATE INDEX IF NOT EXISTS idx_jobs_group ON jobs(keyword_group);

CREATE TABLE IF NOT EXISTS fetch_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL,
    platform      TEXT NOT NULL,
    keyword_group TEXT DEFAULT '',
    keyword       TEXT DEFAULT '',
    status        TEXT NOT NULL,              -- ok | empty | auth_failed | error
    items_new     INTEGER DEFAULT 0,
    items_updated INTEGER DEFAULT 0,
    items_total   INTEGER DEFAULT 0,
    error_text    TEXT DEFAULT '',
    started_at    TEXT NOT NULL,
    finished_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_time ON fetch_runs(started_at DESC);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path = DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------- 岗位 ----------

    def upsert_jobs(self, items: list[JobItem], keyword_group: str,
                    job_type: str) -> tuple[int, int]:
        """批量入库。返回 (新增数, 更新数)。first_seen 不变，miss 清零。"""
        if not items:
            return 0, 0
        existing = {r[0] for r in self.conn.execute("SELECT dedup_key FROM jobs")}
        ts = now()
        new = updated = 0
        for it in items:
            s = it.salary
            row = (
                it.dedup_key, it.platform, it.site_job_id, it.title, it.company,
                it.city, it.district, it.salary_text,
                s.min_k if s else None, s.max_k if s else None,
                s.months if s else None,
                it.experience, it.education, it.company_industry,
                it.company_size, it.hr_name,
                json.dumps(it.tags, ensure_ascii=False), it.url,
                it.publish_time_text, keyword_group, job_type,
                ts, ts, "active", 0, ts,
            )
            self.conn.execute(
                """
                INSERT INTO jobs (
                    dedup_key, platform, site_job_id, title, company, city,
                    district, salary_text, salary_min_k, salary_max_k,
                    salary_months, experience, education, company_industry,
                    company_size, hr_name, tags, url, publish_time_text,
                    keyword_group, job_type, first_seen_at, last_seen_at,
                    last_status, miss_count, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(dedup_key) DO UPDATE SET
                    title=excluded.title, company=excluded.company,
                    city=excluded.city, district=excluded.district,
                    salary_text=excluded.salary_text,
                    salary_min_k=excluded.salary_min_k,
                    salary_max_k=excluded.salary_max_k,
                    salary_months=excluded.salary_months,
                    experience=excluded.experience, education=excluded.education,
                    company_industry=excluded.company_industry,
                    company_size=excluded.company_size, hr_name=excluded.hr_name,
                    tags=excluded.tags, url=excluded.url,
                    publish_time_text=excluded.publish_time_text,
                    keyword_group=excluded.keyword_group,
                    job_type=excluded.job_type,
                    last_seen_at=excluded.last_seen_at,
                    last_status='active', miss_count=0,
                    updated_at=excluded.updated_at
                """,
                row,
            )
            if it.dedup_key in existing:
                updated += 1
            else:
                new += 1
        self.conn.commit()
        return new, updated

    def mark_misses(self, platform: str, seen_keys: set[str],
                    archive_after_misses: int) -> int:
        """本平台本轮未见到的在招岗位 miss+1；累计达标则归档。返回归档数。"""
        rows = self.conn.execute(
            "SELECT dedup_key FROM jobs WHERE platform=? AND last_status='active'",
            (platform,),
        ).fetchall()
        missed = [r[0] for r in rows if r[0] not in seen_keys]
        archived = 0
        ts = now()
        for key in missed:
            cur = self.conn.execute(
                "UPDATE jobs SET miss_count=miss_count+1, updated_at=? WHERE dedup_key=?",
                (ts, key),
            )
            cnt = self.conn.execute(
                "SELECT miss_count FROM jobs WHERE dedup_key=?", (key,)
            ).fetchone()[0]
            if cnt >= archive_after_misses:
                self.conn.execute(
                    "UPDATE jobs SET last_status='archived' WHERE dedup_key=?", (key,)
                )
                archived += 1
        self.conn.commit()
        return archived

    def cleanup_archived(self, keep_days: int = 180) -> int:
        """删除归档超过 keep_days 天的记录（尊重源站下线，定期清理）。"""
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat(timespec="seconds")
        cur = self.conn.execute(
            "DELETE FROM jobs WHERE last_status='archived' AND updated_at < ?", (cutoff,)
        )
        self.conn.commit()
        return cur.rowcount

    # ---------- UI 查询 ----------

    def query_jobs(self, *, platforms: list[str] | None = None,
                   groups: list[str] | None = None, job_type: str = "",
                   fresh_days: int | None = None, salary_min_k: float | None = None,
                   search: str = "", include_archived: bool = False,
                   order: str = "last_seen", limit: int = 500) -> list[dict]:
        """按 UI 筛选条件查岗位。search 为空格分隔多词 AND（匹配职位/公司）。"""
        where: list[str] = []
        args: list = []
        if not include_archived:
            where.append("last_status='active'")
        if platforms:
            where.append(f"platform IN ({','.join('?' * len(platforms))})")
            args += platforms
        if groups:
            where.append(f"keyword_group IN ({','.join('?' * len(groups))})")
            args += groups
        if job_type:
            where.append("job_type=?")
            args.append(job_type)
        if fresh_days is not None:
            cutoff = (datetime.now() - timedelta(days=fresh_days)) \
                .isoformat(timespec="seconds")
            where.append("last_seen_at>=?")
            args.append(cutoff)
        if salary_min_k is not None:
            where.append("salary_max_k>=?")   # 区间上限达线即算（不卡死下限）
            args.append(salary_min_k)
        for term in (search or "").split():
            where.append("(title LIKE ? OR company LIKE ?)")
            args += [f"%{term}%", f"%{term}%"]
        order_sql = {
            "last_seen": "last_seen_at DESC",
            "new_first": "first_seen_at DESC",
            "salary": "(salary_max_k IS NULL), salary_max_k DESC",
        }.get(order, "last_seen_at DESC")
        sql = f"SELECT * FROM jobs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY {order_sql} LIMIT ?"
        args.append(limit)
        rows = self.conn.execute(sql, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d.get("tags") or "[]")
            out.append(d)
        return out

    def count_by_group(self, *, platforms: list[str] | None = None,
                       job_type: str = "", fresh_days: int | None = None,
                       salary_min_k: float | None = None, search: str = "",
                       include_archived: bool = False) -> dict[str, int]:
        """同 query_jobs 的筛选条件（不含方向），按方向返回精确计数。"""
        where: list[str] = []
        args: list = []
        if not include_archived:
            where.append("last_status='active'")
        if platforms:
            where.append(f"platform IN ({','.join('?' * len(platforms))})")
            args += platforms
        if job_type:
            where.append("job_type=?")
            args.append(job_type)
        if fresh_days is not None:
            cutoff = (datetime.now() - timedelta(days=fresh_days)) \
                .isoformat(timespec="seconds")
            where.append("last_seen_at>=?")
            args.append(cutoff)
        if salary_min_k is not None:
            where.append("salary_max_k>=?")
            args.append(salary_min_k)
        for term in (search or "").split():
            where.append("(title LIKE ? OR company LIKE ?)")
            args += [f"%{term}%", f"%{term}%"]
        sql = "SELECT keyword_group, COUNT(*) AS n FROM jobs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " GROUP BY keyword_group"
        return {r["keyword_group"] or "未分组": r["n"]
                for r in self.conn.execute(sql, args).fetchall()}

    def stats(self) -> dict:
        """顶部指标：在招总数 / 今日新增 / 公司数。"""
        row = self.conn.execute(
            """SELECT
                 COUNT(*) FILTER (WHERE last_status='active') AS active_total,
                 COUNT(*) FILTER (WHERE last_status='active'
                                   AND substr(first_seen_at,1,10)=?) AS today_new,
                 COUNT(DISTINCT company) FILTER (WHERE last_status='active') AS companies
               FROM jobs""",
            (datetime.now().strftime("%Y-%m-%d"),),
        ).fetchone()
        return dict(row)

    # ---------- 运行记录 ----------

    def record_run(self, run_id: str, platform: str, keyword_group: str,
                   keyword: str, status: str, *, items_new: int = 0,
                   items_updated: int = 0, items_total: int = 0,
                   error_text: str = "", started_at: str = "",
                   finished_at: str = "") -> None:
        self.conn.execute(
            """INSERT INTO fetch_runs (run_id, platform, keyword_group, keyword,
               status, items_new, items_updated, items_total, error_text,
               started_at, finished_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, platform, keyword_group, keyword, status, items_new,
             items_updated, items_total, error_text,
             started_at or now(), finished_at or now()),
        )
        self.conn.commit()

    def latest_status_by_platform(self) -> dict[str, dict]:
        """每平台最近一次运行的状态（UI 顶部胶囊用）。"""
        rows = self.conn.execute(
            """SELECT platform, status, started_at, items_new, error_text
               FROM fetch_runs f
               WHERE id = (SELECT MAX(id) FROM fetch_runs
                           WHERE platform = f.platform)"""
        ).fetchall()
        return {r["platform"]: dict(r) for r in rows}

    def close(self) -> None:
        self.conn.close()
