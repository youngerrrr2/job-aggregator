"""Streamlit 本地 UI：岗位筛选浏览 + 跳转原文 + 抓取状态与手动触发。

启动：双击 start_ui.bat（或命令行 streamlit run app.py）
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from jobaggregator.config import load_config          # noqa: E402
from jobaggregator.db import Database                 # noqa: E402
from jobaggregator.paths import LOCK_PATH             # noqa: E402

PLATFORM_NAMES = {"liepin": "猎聘", "job51": "前程无忧",
                  "zhaopin": "智联招聘", "zhipin": "BOSS直聘"}
STATUS_BADGE = {"ok": "🟢", "empty": "🟡", "auth_failed": "🔒", "error": "🔴"}
FRESH_OPTIONS = ["全部", "今天", "近3天", "近7天", "近14天", "近30天"]
FRESH_DAYS = {"全部": None, "今天": 1, "近3天": 3, "近7天": 7,
              "近14天": 14, "近30天": 30}
ORDER_OPTIONS = {"最近抓到": "last_seen", "最新发现": "new_first",
                 "薪资从高到低": "salary"}

cfg = load_config(ROOT / "config.yaml")

st.set_page_config(page_title="财务岗位聚合", page_icon="🧭", layout="wide")
st.title(f"🧭 财务岗位聚合 · {cfg.city}")


def load_data(filters: dict) -> tuple[pd.DataFrame, dict, dict]:
    db = Database()
    try:
        rows = db.query_jobs(**filters)
        return pd.DataFrame(rows), db.stats(), db.latest_status_by_platform()
    finally:
        db.close()


# ---------- 侧栏筛选 ----------

with st.sidebar:
    st.header("筛选")
    enabled_platforms = [n for n, p in cfg.platforms.items() if p.enabled]
    f_platforms = st.multiselect(
        "平台", enabled_platforms, default=enabled_platforms,
        format_func=lambda n: PLATFORM_NAMES.get(n, n))
    all_groups = [g.name for g in cfg.keyword_groups]
    f_groups = st.multiselect("方向", all_groups, default=all_groups)
    f_job_type = st.radio("岗位性质", ["全部", "全职", "实习"], horizontal=True)
    default_fresh = next((k for k, v in FRESH_DAYS.items()
                          if v == cfg.ui.get("default_fresh_days")), "近14天")
    f_fresh = st.selectbox("新鲜度（最近还在挂）", FRESH_OPTIONS,
                           index=FRESH_OPTIONS.index(default_fresh))
    f_salary = st.slider("月薪不低于（K，按区间上限）", 0, 60, 0, step=1)
    f_search = st.text_input("关键词（空格分隔，职位/公司 AND 匹配）")
    f_active_only = st.checkbox("只看在招", value=True)
    f_order = st.selectbox("排序", list(ORDER_OPTIONS))

filters = {
    "platforms": f_platforms or None,
    "groups": f_groups or None,
    "job_type": "" if f_job_type == "全部" else f_job_type,
    "fresh_days": FRESH_DAYS[f_fresh],
    "salary_min_k": float(f_salary) if f_salary > 0 else None,
    "search": f_search.strip(),
    "include_archived": not f_active_only,
    "order": ORDER_OPTIONS[f_order],
    "limit": 1000,
}

df, stats, run_status = load_data(filters)

# ---------- 顶部：指标 + 平台状态 + 抓取按钮 ----------

m1, m2, m3, m4 = st.columns([1.2, 1.2, 1.2, 1.6])
m1.metric("在招岗位", stats.get("active_total") or 0)
m2.metric("今日新增", stats.get("today_new") or 0)
m3.metric("涉及公司", stats.get("companies") or 0)

fetching = LOCK_PATH.exists()
if m4.button("🫙 立即抓取", type="primary", disabled=fetching, use_container_width=True):
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    cmd = str(pythonw if pythonw.exists() else exe)
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.Popen([cmd, "run_fetch.py"], cwd=str(ROOT), creationflags=flags)
    st.toast("已启动后台抓取，一两分钟后刷新页面查看", icon="🚀")
    st.rerun()
if fetching:
    m4.caption("⏳ 抓取进行中…（完成后自动解锁）")

if run_status:
    pills = []
    for name in enabled_platforms:
        s = run_status.get(name)
        if not s:
            pills.append(f"⚪ {PLATFORM_NAMES.get(name, name)} 未抓取")
            continue
        t = ""
        try:
            t = datetime.fromisoformat(s["started_at"]).strftime("%m-%d %H:%M")
        except ValueError:
            t = s["started_at"][:16]
        badge = STATUS_BADGE.get(s["status"], "⚪")
        label = f"{badge} {PLATFORM_NAMES.get(name, name)} {t}"
        if s.get("error_text"):
            st.markdown(
                f'<span title="{s["error_text"][:200]}">{label}</span>',
                unsafe_allow_html=True)
            continue
        pills.append(label)
    st.markdown("　".join(pills))

# ---------- 主表 ----------

if df.empty:
    st.info("没有符合条件的岗位。试试放宽筛选，或点右上「立即抓取」先抓一轮。")
    st.stop()

today = datetime.now().strftime("%Y-%m-%d")
df["今日新"] = df["first_seen_at"].astype(str).str.slice(0, 10).apply(
    lambda d: "🆕" if d == today else "")
df["月薪K"] = (df["salary_min_k"] + df["salary_max_k"]) / 2
df["平台"] = df["platform"].map(PLATFORM_NAMES).fillna(df["platform"])
df["地点"] = (df["city"] + "-" + df["district"]).str.rstrip("-")

table = df[["今日新", "title", "company", "salary_text", "月薪K", "keyword_group",
            "平台", "地点", "experience", "education", "url", "dedup_key"]] \
    .rename(columns={"title": "职位", "company": "公司", "salary_text": "薪资",
                     "keyword_group": "方向", "experience": "经验",
                     "education": "学历", "url": "原文"})

st.caption(f"共 {len(table)} 条（在招，按{f_order}，最多 1000 条）")
event = st.dataframe(
    table,
    column_config={
        "原文": st.column_config.LinkColumn(display_text="🔗 打开", width="small"),
        "月薪K": st.column_config.NumberColumn(format="%.1f"),
    },
    hide_index=True, use_container_width=True, height=620,
    on_select="rerun", selection_mode="single-row",
)

sel = event.selection.rows
if sel:
    row = df.iloc[sel[0]]
    with st.expander(f"📌 {row['title']} — {row['company']}", expanded=True):
        c1, c2 = st.columns([3, 2])
        with c1:
            st.write(f"**薪资**：{row['salary_text'] or '面议'}　"
                     f"**经验**：{row['experience'] or '-'}　"
                     f"**学历**：{row['education'] or '-'}")
            st.write(f"**公司**：{row['company']}　{row['company_industry']}　"
                     f"{row['company_size']}")
            st.write(f"**联系人**：{row['hr_name'] or '-'}")
            if isinstance(row["tags"], list) and row["tags"]:
                st.write("标签：" + "　".join(f"`{t}`" for t in row["tags"]))
        with c2:
            st.write(f"**方向**：{row['keyword_group']}（{row['job_type']}）")
            st.write(f"**发布**：{row['publish_time_text'] or '-'}")
            st.write(f"**首次发现**：{row['first_seen_at'][:16].replace('T', ' ')}")
            st.write(f"**最近抓到**：{row['last_seen_at'][:16].replace('T', ' ')}")
            st.link_button("跳转原文 ↗", row["url"])

st.download_button(
    "⬇️ 导出当前筛选结果 CSV",
    data=table.drop(columns=["dedup_key", "今日新"]).to_csv(index=False)
        .encode("utf-8-sig"),
    file_name=f"岗位_{datetime.now():%Y%m%d_%H%M}.csv",
    mime="text/csv",
)
st.caption("数据仅供个人浏览；岗位详情与时效以各平台原文为准。")
