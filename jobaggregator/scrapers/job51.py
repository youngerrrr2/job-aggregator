"""前程无忧 51job 抓取插件：浏览器打开搜索页，拦截 search-pc 接口（免登录）。

接口探测记录（2026-10，scripts/capture_api.py 抓包）：
  页面 https://we.51job.com/pc/search?keyword=…&searchType=2&jobArea=020000
  自行 GET we.51job.com/api/job/search-pc?…&decode__1048=<签名>
  （签名由页面 JS 生成，纯 requests 无法直连——阿里云 WAF）
  响应：{"status":"1","resultbody":{"job":{"items":[…]}}}
    {jobId, jobName, jobTags[], provideSalaryString("2-3万·15薪"),
     workYearString, degreeString, jobAreaString("上海-徐汇区"),
     companyName, companyTypeString, companySizeString,
     companyIndustryType1Str, hrName, issueDateString, isIntern, jobHref}
  城市码：上海=020000（URL 参数 jobArea）。
改版后校准：python scripts/capture_api.py job51
"""

from __future__ import annotations

from typing import Iterator, Optional
from urllib.parse import quote

from ..errors import ScraperError
from ..models import JobItem, parse_salary
from ..registry import register
from .base import BaseScraper

SEARCH_URL = "https://we.51job.com/pc/search?keyword={key}&searchType=2&jobArea={area}"
API_MARK = "we.51job.com/api/job/search-pc"


@register
class Job51Scraper(BaseScraper):
    platform = "job51"
    city_codes = {"上海": "020000"}

    def start(self, engine) -> None:
        super().start(engine)
        self._pages.append(engine.fresh_page())

    def search(self, keyword: str, city: str) -> Iterator[JobItem]:
        area = self.city_code(city, default="")
        if not area:
            self.log.warning("未知城市「%s」无 jobArea 码，按全国（000000）抓取", city)
            area = "000000"
        url = SEARCH_URL.format(key=quote(keyword), area=area)
        data = self.fetch_api_json(url, API_MARK)
        if str(data.get("status")) != "1":
            raise ScraperError(
                f"51job 接口返回异常：status={data.get('status')} "
                f"message={data.get('message')}")
        items = ((data.get("resultbody") or {}).get("job") or {}).get("items") or []
        for it in items:
            item = self._parse_item(it)
            if item is not None:
                yield item

    @staticmethod
    def _parse_item(it: dict) -> Optional[JobItem]:
        jid = str(it.get("jobId") or "")
        title = it.get("jobName") or ""
        if not jid or not title:
            return None
        href = it.get("jobHref") or ""
        if href.startswith("/"):
            href = "https://we.51job.com" + href
        area = (it.get("jobAreaString") or "").replace("·", "-")
        city_part, _, district = area.partition("-")
        return JobItem(
            platform="job51",
            site_job_id=jid,
            title=title,
            url=href,
            company=it.get("companyName") or "",
            city=city_part,
            district=district,
            salary_text=it.get("provideSalaryString") or "",
            salary=parse_salary(it.get("provideSalaryString")),
            experience=it.get("workYearString") or "",
            education=it.get("degreeString") or "",
            company_industry=it.get("companyIndustryType1Str") or "",
            company_size=it.get("companySizeString") or "",
            hr_name=it.get("hrName") or "",
            tags=list(it.get("jobTags") or []),
            publish_time_text=it.get("issueDateString") or "",
        )
