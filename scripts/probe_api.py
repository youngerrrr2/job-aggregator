"""各大招聘平台接口可用性探测（开发工具）——第二轮：错误详情 + 接口变体。

用法：
    python scripts/probe_api.py            # 探测全部平台
    python scripts/probe_api.py liepin     # 只探测猎聘

每个平台只发少量请求，输出真实响应详情，用于决定/校准抓取策略。请勿高频运行。
"""
from __future__ import annotations

import json
import sys
import time

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
COMMON = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _dump_json(data, indent=2, limit=3000) -> str:
    return json.dumps(data, ensure_ascii=False, indent=indent)[:limit]


def _print_result(tag: str, r: requests.Response) -> dict | None:
    print(f"\n--- {tag}")
    print(f"  HTTP {r.status_code} | {r.headers.get('Content-Type', '')}")
    if r.text[:1] in "{[":
        try:
            data = r.json()
        except Exception:
            print(f"  解析失败，前300字符: {r.text[:300]!r}")
            return None
        body_str = _dump_json(data)
        if len(body_str) < 1500:
            print(f"  完整响应:\n{body_str}")
        else:
            print(f"  顶层字段: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            print(f"  响应前1500字符:\n{body_str[:1500]}")
        return data
    print(f"  非JSON（长度 {len(r.text)}），前200字符: {r.text[:200]!r}")
    return None


def probe_liepin() -> None:
    print("=" * 60)
    print("【猎聘】错误详情 + 变体尝试")
    url = "https://api-c.liepin.com/api/com.liepin.searchfront4c.pc-search-job"
    payload = {
        "data": {
            "mainSearchPcConditionForm": {
                "city": "410", "dq": "410", "pubTime": "", "currentPage": 0,
                "pageSize": 10, "key": "财务分析", "suggestTag": "", "workYearCode": "0",
                "compId": "", "compName": "", "compTag": "", "industry": "", "salary": "",
                "jobKind": "", "compScale": "", "compKind": "", "compStage": "", "eduLevel": "",
            },
            "passThroughForm": {"scene": "page", "skId": "", "fkId": "", "ckId": ""},
        }
    }
    headers = {
        **COMMON,
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://www.liepin.com",
        "Referer": "https://www.liepin.com/",
    }

    s = requests.Session()
    s.headers.update(headers)

    # 变体1：原样重试，打印完整小响应（看 flag/code/msg 内容）
    r = s.post(url, json=payload, timeout=15)
    data = _print_result("变体1：原 payload", r)

    # 若失败，尝试 currentPage 从 1 开始（有的平台从 1 计数）
    if not (isinstance(data, dict) and data.get("flag") == 1):
        time.sleep(3)
        p2 = json.loads(json.dumps(payload))
        p2["data"]["mainSearchPcConditionForm"]["currentPage"] = 1
        r = s.post(url, json=p2, timeout=15)
        data = _print_result("变体2：currentPage=1", r)

    # 仍失败则尝试带上 kid 查询参数（新版猎聘有的接口要求）
    if not (isinstance(data, dict) and data.get("flag") == 1):
        time.sleep(3)
        r = s.post(url, params={"kid": "0"}, json=payload, timeout=15)
        _print_result("变体3：带 kid=0 查询参数", r)


def probe_job51() -> None:
    print("=" * 60)
    print("【前程无忧】多变体尝试")
    base_headers = {
        **COMMON,
        "Origin": "https://we.51job.com",
        "Referer": "https://we.51job.com/pc/search?keyword=%E8%B4%A2%E5%8A%A1%E5%88%86%E6%9E%90&searchType=2&jobArea=020000",
        "X-Requested-With": "XMLHttpRequest",
    }
    payload = {
        "searchType": 2, "function": "", "industry": "", "jobArea": "020000",
        "jobArea2": "", "jobDegree": "", "jobSalary": "", "keyword": "财务分析",
        "keywordType": 2, "lat": "", "lon": "", "orderType": 0, "pageNo": 1,
        "pageSize": 20, "postId": "", "salary": "", "workYear": "",
    }
    s = requests.Session()
    s.headers.update(base_headers)

    # 先访问一次首页拿初始 cookie（不少站点要求先有 cookie 才给 API）
    try:
        s.get("https://we.51job.com/pc/search", timeout=15)
        print(f"\n[预热] 首页 cookie: {list(s.cookies.keys())}")
    except Exception as e:
        print(f"\n[预热] 首页异常: {e!r}")

    time.sleep(2)
    # 变体1：POST application/json（原方案）
    r = s.post("https://we.51job.com/api/job/search-job",
               json=payload, headers={"Content-Type": "application/json"}, timeout=15)
    _print_result("变体1：POST /api/job/search-job (json)", r)

    time.sleep(2)
    # 变体2：POST x-www-form-urlencoded
    r = s.post("https://we.51job.com/api/job/search-job", data=payload, timeout=15)
    _print_result("变体2：POST form 表单", r)

    time.sleep(2)
    # 变体3：GET 同路径带查询参数
    r = s.get("https://we.51job.com/api/job/search-job", params=payload, timeout=15)
    _print_result("变体3：GET 查询参数", r)

    time.sleep(2)
    # 变体4：另一个已知路径 search-pc
    r = s.post("https://we.51job.com/api/job/search-pc", json=payload, timeout=15)
    _print_result("变体4：POST /api/job/search-pc", r)


def probe_zhaopin() -> None:
    print("=" * 60)
    print("【智联招聘】405 → 尝试 POST 等变体")
    url = "https://fe-api.zhaopin.com/c/i/search/positions"
    params = {
        "kw": "财务分析", "cityId": "538", "start": "0", "pageSize": "20",
        "workExperience": "-1", "education": "-1", "salary": "-1",
        "sortType": "0",
    }
    headers = {**COMMON, "Origin": "https://sou.zhaopin.com", "Referer": "https://sou.zhaopin.com/"}
    s = requests.Session()
    s.headers.update(headers)

    # 变体1：POST 空 body（仅探测方法是否改了）
    r = s.post(url, timeout=15)
    _print_result("变体1：POST 同一路径", r)

    time.sleep(2)
    # 变体2：POST JSON body
    r = s.post(url, json={"kw": "财务分析", "cityId": 538, "start": 0, "pageSize": 20}, timeout=15)
    _print_result("变体2：POST JSON body", r)

    time.sleep(2)
    # 变体3：新路径 lpc/positions（智联新版搜索有的走这个）
    r = s.get("https://fe-api.zhaopin.com/c/i/lpc/positions",
              params=params, timeout=15)
    _print_result("变体3：GET /c/i/lpc/positions", r)


def probe_zhipin() -> None:
    print("=" * 60)
    print("【BOSS直聘】wapi 响应详情（看 code/message/zpData 内容）")
    url = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"
    params = {"scene": "1", "query": "财务分析", "city": "101020100",
              "experience": "", "payType": "", "partTime": "", "degree": "",
              "industry": "", "scale": "", "stage": "", "position": "",
              "jobType": "", "salary": "", "multiBusinessDistrict": "",
              "multiSubway": "", "page": "1", "pageSize": "30"}
    headers = {**COMMON, "Referer": "https://www.zhipin.com/web/geek/job"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        _print_result("wapi 无登录详情", r)
    except Exception as e:
        print(f"  请求异常: {e!r}")


PROBES = {
    "liepin": probe_liepin,
    "job51": probe_job51,
    "zhaopin": probe_zhaopin,
    "zhipin": probe_zhipin,
}


def main() -> None:
    if sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    names = sys.argv[1:] or list(PROBES)
    for name in names:
        fn = PROBES.get(name)
        if fn is None:
            print(f"未知平台: {name}（可选: {', '.join(PROBES)}）")
            continue
        fn()
        time.sleep(3)


if __name__ == "__main__":
    main()
