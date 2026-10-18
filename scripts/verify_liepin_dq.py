"""一次性验证：URL 参数 dq=020 / city=020 哪个能让猎聘搜索请求体带上上海 dq。

每种写法加载一次页面，捕获 pc-search-job 的 JSON POST（body 以 {"data" 开头），
把 mainSearchPcConditionForm.city/dq 与前 3 张卡的 dq 落盘对比。

用法：python scripts/verify_liepin_dq.py
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
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
CANDIDATES = [
    ("dq=020", "https://www.liepin.com/zhaopin/?key=" + quote("财务分析") + "&dq=020"),
    ("city=020", "https://www.liepin.com/zhaopin/?key=" + quote("财务分析") + "&city=020"),
]


def main() -> None:
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        ctx = browser.new_context(user_agent=UA, locale="zh-CN",
                                  viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        for tag, url in CANDIDATES:
            try:
                with page.expect_response(
                    lambda r: ("pc-search-job" in r.url and r.status == 200
                               and (r.request.post_data or "").lstrip().startswith('{"data"')),
                    timeout=40000,
                ) as info:
                    page.goto(url, timeout=40000, wait_until="domcontentloaded")
                body = info.value.json()
                form = ((body.get("data") or {}).get("data") or {}) \
                    .get("mainSearchPcConditionForm") or {}
                # 响应里表单字段位置可能不同，双保险：直接从请求体取
                if not form:
                    form = json.loads(info.value.request.post_data)["data"] \
                        ["mainSearchPcConditionForm"]
                cards = ((body.get("data") or {}).get("data") or {}) \
                    .get("jobCardList") or []
                dqs = [((c.get("job") or {}).get("dq") or "") for c in cards[:5]]
                sh_cnt = sum(1 for c in cards
                             if ((c.get("job") or {}).get("dq") or "").startswith("上海"))
                results.append({
                    "tag": tag, "url": url,
                    "form_city": form.get("city"), "form_dq": form.get("dq"),
                    "flag": body.get("flag"), "n_cards": len(cards),
                    "shanghai_count": sh_cnt, "first_5_dqs": dqs,
                })
                print(f"{tag}: form_dq={form.get('dq')} n={len(cards)} sh={sh_cnt}")
            except Exception as e:
                results.append({"tag": tag, "error": repr(e)})
                print(f"{tag}: ERROR {e!r}")
            page.wait_for_timeout(5000)
        browser.close()
    (OUT / "dq_verify.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved data/captures/dq_verify.json")


if __name__ == "__main__":
    main()
