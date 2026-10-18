"""一次性校准：智联 SSR 搜索页里岗位数据的载体（嵌入 JSON 还是纯 DOM）。

落盘 data/captures/zhaopin_sou.html，并打标记：
  __INITIAL_STATE__ / __NEXT_DATA__ / positionName 出现与否

用法：python scripts/calibrate_zhaopin.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

OUT = ROOT / "data" / "captures"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
URL = "https://sou.zhaopin.com/?jl=538&kw=" + quote("财务分析")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        ctx = browser.new_context(user_agent=UA, locale="zh-CN",
                                  viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(URL, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(12000)
        html = page.content()
        (OUT / "zhaopin_sou.html").write_text(html, encoding="utf-8")
        for marker in ("__INITIAL_STATE__", "__NEXT_DATA__", "positionName",
                       "joblist", "salary", "安全验证"):
            print(f"{marker}: {html.count(marker)}")
        print("html_len:", len(html))
        browser.close()


if __name__ == "__main__":
    main()
