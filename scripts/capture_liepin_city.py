"""用真实浏览器打开猎聘「上海」搜索页，捕获全部 JSON 接口请求 + 截图。

目的：拿到上海的 dq 城市码（上次抓包默认 410=全国）。
产出：data/captures/liepin_shanghai.json + liepin_shanghai.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "data" / "captures"


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    url = "https://www.liepin.com/zhaopin/?key=财务分析&city=上海"
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=False)
        except Exception as e:
            print(f"系统 Chrome 启动失败（{e!r}），回退自带 Chromium")
            browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900}, locale="zh-CN"
        )
        page = ctx.new_page()
        records: list[dict] = []

        def on_response(resp):
            try:
                ct = resp.headers.get("content-type", "")
                if "json" not in ct.lower():
                    return
                records.append(
                    {
                        "url": resp.url,
                        "status": resp.status,
                        "method": resp.request.method,
                        "post_data": resp.request.post_data,
                        "body_head": "",
                    }
                )
                try:
                    records[-1]["body_head"] = json.dumps(
                        resp.json(), ensure_ascii=False
                    )[:800]
                except Exception:
                    pass
            except Exception:
                pass

        page.on("response", on_response)
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(10000)
        page.screenshot(path=str(OUT / "liepin_shanghai.png"))
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "liepin_shanghai.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"捕获 {len(records)} 个 JSON 响应：")
        for r in records:
            print(f"  {r['method']} [{r['status']}] {r['url'][:120]}")
        browser.close()


if __name__ == "__main__":
    main()
