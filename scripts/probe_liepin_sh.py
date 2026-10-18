"""猎聘 requests 直连验证 v2：先拿首页 Cookie，再调 API；非 JSON 时打印原始内容。"""
from __future__ import annotations

import json
import sys
import time

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Origin": "https://www.liepin.com",
    "Referer": "https://www.liepin.com/",
}
URL = "https://api-c.liepin.com/api/com.liepin.searchfront4c.pc-search-job"


def make_payload(dq: str) -> dict:
    return {
        "data": {
            "mainSearchPcConditionForm": {
                "city": dq, "dq": dq, "pubTime": "", "currentPage": 0,
                "pageSize": 10, "key": "财务分析", "suggestTag": "",
                "workYearCode": "", "compId": "", "compName": "", "compTag": "",
                "industry": "", "salaryCode": "", "jobKind": "", "compScale": "",
                "compKind": "", "compStage": "", "eduLevel": "",
                "salaryLow": "", "salaryHigh": "",
            },
            "passThroughForm": {
                "scene": "init", "skId": "", "fkId": "", "ckId": "", "suggest": None
            },
        }
    }


def call(s: requests.Session, tag: str, dq: str) -> dict | None:
    r = s.post(URL, json=make_payload(dq),
               headers={"Content-Type": "application/json;charset=UTF-8"},
               timeout=20)
    print(f"\n--- {tag} (dq={dq}) → HTTP {r.status_code}, 长度 {len(r.text)}")
    if r.text[:1] not in "{[":
        print(f"  ⚠️ 非JSON，前400字符：\n{r.text[:400]}")
        return None
    data = r.json()
    if data.get("flag") == 1:
        cards = data.get("data", {}).get("data", {}).get("jobCardList", [])
        print(f"  ✅ 成功！返回 {len(cards)} 张职位卡")
        for c in cards[:3]:
            job, comp = c.get("job", {}), c.get("comp", {})
            print(f"    {job.get('title')} | {job.get('salary')} | {job.get('dq')} | {comp.get('compName')}")
    else:
        print(f"  ❌ flag={data.get('flag')} code={data.get('code')} msg={data.get('msg')}")
        print(f"  完整响应前500字符: {json.dumps(data, ensure_ascii=False)[:500]}")
    return data


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    s = requests.Session()
    s.headers.update(HEADERS)

    # 步骤1：先 GET 首页拿初始 Cookie（有 JS 挑战的话看拿到的 cookie 名）
    try:
        r = s.get("https://www.liepin.com/", timeout=20)
        print(f"[预热] 首页 HTTP {r.status_code}, 长度 {len(r.text)}")
        print(f"[预热] cookies: {list(s.cookies.keys())}")
    except Exception as e:
        print(f"[预热] 异常: {e!r}")

    time.sleep(4)
    call(s, "重放payload+首页Cookie", "410")


if __name__ == "__main__":
    main()
