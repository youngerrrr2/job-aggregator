"""一次性诊断：让猎聘页面自己暴露「上海 → dq 码」映射（匿名、单次加载）。

做法：打开一次搜索页，落盘
  data/captures/dq_apis.json   所有 200 且 body 为 JSON 的接口响应（含请求体）
  data/captures/dq_page.html   渲染后的页面 HTML
  data/captures/dq_hits.txt    本地正则筛出的「上海」附近含数字码的片段
然后人工看 dq_hits.txt 定上海的 dq 码。

用法：python scripts/discover_liepin_dq.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

OUT = ROOT / "data" / "captures"
OUT.mkdir(parents=True, exist_ok=True)

URL = "https://www.liepin.com/zhaopin/?key=" + quote("财务分析")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

captured: list[dict] = []


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        ctx = browser.new_context(user_agent=UA, locale="zh-CN",
                                  viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        def on_response(r):
            if r.status != 200:
                return
            try:
                body = r.text()
            except Exception:
                return
            if body.lstrip()[:1] in ("{", "["):
                captured.append({
                    "url": r.url,
                    "method": r.request.method,
                    "post_data": (r.request.post_data or "")[:2000],
                    "body": body[:300000],
                })

        page.on("response", on_response)
        page.goto(URL, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(12000)

        html = page.content()
        (OUT / "dq_page.html").write_text(html, encoding="utf-8")
        (OUT / "dq_apis.json").write_text(
            json.dumps(captured, ensure_ascii=False, indent=1), encoding="utf-8")

        # 本地筛：上海 附近 60 字符窗口内出现 3-8 位数字的片段
        pat = re.compile(r".{0,60}上海.{0,60}")
        hits: list[tuple[str, str]] = []
        blobs = [("html", html)] + [(a["url"][:100], a["body"]) for a in captured]
        for name, blob in blobs:
            for m in pat.finditer(blob):
                s = m.group(0)
                if re.search(r"\d{3,8}", s):
                    hits.append((name, s.replace("\n", " ")))
        report = "\n\n".join(f"--- {n} ---\n{s}" for n, s in hits[:120])
        (OUT / "dq_hits.txt").write_text(report or "(no hits)", encoding="utf-8")

        # 基线：真 JSON POST 的搜索请求体里的 dq（确认当前默认值）
        for a in captured:
            if "pc-search-job" in a["url"] and a["post_data"].lstrip().startswith('{"data"'):
                (OUT / "dq_search_post.txt").write_text(a["post_data"], encoding="utf-8")
                break

        print(f"json_apis={len(captured)} hits={len(hits)} "
              f"files=dq_hits.txt,dq_apis.json,dq_page.html")
        browser.close()


if __name__ == "__main__":
    main()
