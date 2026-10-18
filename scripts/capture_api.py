"""用真实浏览器打开各平台搜索页，捕获网站自己发出的搜索 API 请求/响应（自动抓包）。

用法：
    python scripts/capture_api.py             # 全部平台
    python scripts/capture_api.py liepin zhipin

产出：
    data/captures/<platform>.json   该页面所有 JSON 接口的 URL / 请求体 / 响应样本
    data/captures/<platform>.png    页面截图（判断是否遇到登录墙/验证码）

这是开发工具：网站改版后重跑一次即可重新校准各 scraper 的接口参数。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "captures"

TARGETS = {
    "liepin": "https://www.liepin.com/zhaopin/?key=财务分析",
    "zhaopin": "https://sou.zhaopin.com/?kw=财务分析&jl=538",
    "job51": "https://we.51job.com/pc/search?keyword=财务分析&searchType=2&jobArea=020000",
    "zhipin": "https://www.zhipin.com/web/geek/job?query=财务分析&city=101020100",
}

WAIT_SEC = 12  # 每个页面等待 JS 挑战/接口返回的时间


def capture(pages_arg: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    names = pages_arg or list(TARGETS)
    with sync_playwright() as p:
        # 优先用系统 Chrome（真实指纹），失败回退 Playwright 自带 Chromium
        try:
            browser = p.chromium.launch(channel="chrome", headless=False)
        except Exception as e:
            print(f"系统 Chrome 启动失败（{e!r}），回退自带 Chromium")
            browser = p.chromium.launch(headless=False)

        for name in names:
            url = TARGETS.get(name)
            if not url:
                print(f"未知平台: {name}")
                continue
            print(f"\n===== {name}: {url}")
            records: list[dict] = []
            ctx = browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="zh-CN",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
                ),
            )
            page = ctx.new_page()

            def on_response(resp, _name=name):
                try:
                    ct = resp.headers.get("content-type", "")
                    if "json" not in ct.lower():
                        return
                    body = resp.json()
                    records.append(
                        {
                            "url": resp.url,
                            "status": resp.status,
                            "request": {
                                "method": resp.request.method,
                                "post_data": resp.request.post_data,
                            },
                            "body_head": json.dumps(body, ensure_ascii=False)[:4000],
                        }
                    )
                except Exception:
                    pass

            page.on("response", on_response)
            try:
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(WAIT_SEC * 1000)
                page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
                print(f"  截图: data/captures/{name}.png")
            except Exception as e:
                print(f"  页面异常: {e!r}")
                try:
                    page.screenshot(path=str(OUT / f"{name}.png"))
                except Exception:
                    pass

            outfile = OUT / f"{name}.json"
            outfile.write_text(
                json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            interesting = [r for r in records if any(k in r["url"] for k in ("search", "job", "position", "list"))]
            print(f"  捕获 JSON 接口 {len(records)} 个（疑似搜索相关 {len(interesting)} 个）→ {outfile}")
            for r in interesting[:8]:
                print(f"    * {r['request']['method']} {r['url'][:130]}")
            ctx.close()
            time.sleep(3)
        browser.close()


def main() -> None:
    if sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    capture(sys.argv[1:])


if __name__ == "__main__":
    main()
