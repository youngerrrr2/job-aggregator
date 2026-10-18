"""智联招聘抓取插件：SSR 搜索页文档里挖 window.__INITIAL_STATE__（免登录）。

探测记录（2026-10，scripts/calibrate_zhaopin.py）：
  页面 https://www.zhaopin.com/jobs/?jl=538&kw=财务分析
  （老域名 sou.zhaopin.com 会 301/302 三跳到这里，直接用最终 URL）
  岗位数据在文档内嵌 JSON：<script>__INITIAL_STATE__={"…","positionList":[…]}
  （渲染层薪资显示 ¥---- 只是遮罩，STATE 里 salary60 是真值）
  字段映射：name/number/salary60("8000-11000元")/workCity/cityDistrict/
           workingExp/education/companyName/companySize/industryName/
           jobSkillTags[{"name"}]/publishTime("2026-10-14 20:27:30")/
           positionURL（缺省可用 number 拼 jobdetail 链接）
  城市码（region-relation 接口）：上海=538。
改版后校准：python scripts/calibrate_zhaopin.py
"""

from __future__ import annotations

import json
from typing import Iterator, Optional
from urllib.parse import quote

from ..errors import ScraperError
from ..models import JobItem, parse_salary
from ..registry import register
from .base import BaseScraper

SEARCH_URL = "https://www.zhaopin.com/jobs/?jl={jl}&kw={kw}"
STATE_MARK = "__INITIAL_STATE__"


def _extract_initial_state(html: str) -> dict:
    """从 SSR 文档里抠出 __INITIAL_STATE__ 的 JSON（大括号配平）。"""
    i = html.find(STATE_MARK)
    if i < 0:
        raise ScraperError("智联页面未内嵌 __INITIAL_STATE__（可能被安全验证页拦截）")
    start = html.index("{", i)
    depth = 0
    for j in range(start, min(start + 3_000_000, len(html))):
        c = html[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
    else:
        raise ScraperError("智联 __INITIAL_STATE__ JSON 截断/不完整")
    try:
        state = json.loads(html[start:j + 1])
    except ValueError as e:
        raise ScraperError(f"智联 __INITIAL_STATE__ 解析失败：{e}") from e
    if not isinstance(state, dict):
        raise ScraperError("智联 __INITIAL_STATE__ 不是 JSON 对象")
    return state


@register
class ZhaopinScraper(BaseScraper):
    platform = "zhaopin"
    city_codes = {"上海": "538"}

    def start(self, engine) -> None:
        super().start(engine)
        self._pages.append(engine.fresh_page())

    def search(self, keyword: str, city: str) -> Iterator[JobItem]:
        jl = self.city_code(city, default="")
        if not jl:
            self.log.warning("未知城市「%s」无 jl 码，按上海（538）抓取", city)
            jl = "538"
        url = SEARCH_URL.format(jl=jl, kw=quote(keyword))
        html = self.fetch_page_text(url, "zhaopin.com/jobs")
        state = _extract_initial_state(html)
        for p in state.get("positionList") or []:
            item = self._parse_position(p)
            if item is not None:
                yield item

    @staticmethod
    def _parse_position(p: dict) -> Optional[JobItem]:
        num = str(p.get("number") or "")
        title = p.get("name") or ""
        if not num or not title:
            return None
        tags = [t.get("name") for t in (p.get("jobSkillTags") or []) if t.get("name")]
        if not tags:
            tags = [t.get("value") for t in (p.get("skillLabel") or []) if t.get("value")]
        return JobItem(
            platform="zhaopin",
            site_job_id=num,
            title=title,
            url=p.get("positionURL")
                or f"https://www.zhaopin.com/jobdetail/{num}.htm",
            company=p.get("companyName") or "",
            city=p.get("workCity") or "",
            district=p.get("cityDistrict") or "",
            salary_text=(p.get("salary60") or "").replace("¥", ""),
            salary=parse_salary((p.get("salary60") or "").replace("¥", "")),
            experience=p.get("workingExp") or "",
            education=p.get("education") or "",
            company_industry=p.get("industryName") or "",
            company_size=p.get("companySize") or "",
            tags=tags,
            publish_time_text=(p.get("publishTime") or "")[:16],
        )
