"""一次性校准：附加已登录的真实 Chrome，路由透传捕获 BOSS joblist.json。

BOSS 搜索页加载后会自我跳转，普通 expect_response 读不到响应体
（No resource with given identifier found），所以用 route.fetch() 透传捕获。

前置：scripts/login_zhipin.py 已完成登录，Chrome 在 9333 端口活着。
落盘 data/captures/zhipin_jobs.json。用法：python scripts/calibrate_zhipin.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

OUT = ROOT / "data" / "captures"
PORT = 9333
URL = ("https://www.zhipin.com/web/geek/job?query="
       + quote("财务分析") + "&city=101020100")
ROUTE_GLOB = "**/wapi/zpgeek/search/joblist.json*"


def main() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        holder: dict = {}

        def handler(route):
            resp = route.fetch()
            holder["status"] = resp.status
            holder["body"] = resp.text()
            route.fulfill(response=resp)

        page.route(ROUTE_GLOB, handler)
        try:
            page.goto(URL, timeout=40000, wait_until="domcontentloaded")
            for _ in range(60):            # 等路由命中（最多 30s）
                if "body" in holder:
                    break
                page.wait_for_timeout(500)
        finally:
            page.unroute(ROUTE_GLOB)

        data = json.loads(holder.get("body", "{}")) if holder.get("body") else {}
        (OUT / "zhipin_jobs.json").write_text(
            json.dumps([{"status": holder.get("status"), "body": data}],
                       ensure_ascii=False, indent=1), encoding="utf-8")
        jobs = (data.get("zpData") or {}).get("jobList") or []
        print("code=", data.get("code"), "n_jobs=", len(jobs))
        print("final_url:", page.url[:120])
        browser.close()   # 只断开，Chrome 留着


if __name__ == "__main__":
    main()
