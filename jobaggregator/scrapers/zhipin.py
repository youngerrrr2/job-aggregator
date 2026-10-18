"""BOSS直聘抓取插件：真实 Chrome + CDP 附加，路由透传捕获 joblist.json。

探测记录（2026-10，scripts/calibrate_zhipin.py）：
  - Playwright 启动的浏览器（含 persistent_context）会被 BOSS 风控探测后白屏；
    本机真实 Chrome（独立目录 data/browser_profile_chrome + 调试端口）实测可过
    _security_check。登录一次后 Cookie（wt2 等）留在该目录长期复用。
  - 页面 https://www.zhipin.com/web/geek/job?query=…&city=101020100
    加载后 SPA 自我跳转，expect_response 读不到响应体 → 路由透传捕获
    POST /wapi/zpgeek/search/joblist.json
  - 响应：{"code":0,"zpData":{"jobList":[…]}}；code=37 → 登录失效/安全验证
    字段：encryptJobId/jobName/salaryDesc("12-15K")/cityName/areaDistrict/
      businessDistrict/jobExperience/jobDegree/brandName/brandScaleName/
      brandIndustry/bossName/bossTitle/skills[]/welfareList[]
    详情页：https://www.zhipin.com/job_detail/{encryptJobId}.html
  - 城市码：上海=101020100。

谨慎原则（用户明确要求）：每关键词只 1 页、重试最多 1 次、
出现验证/登录失效立即 AuthExpiredError 停用本平台，绝不硬闯。
改版后校准：python scripts/calibrate_zhipin.py
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import quote

from ..errors import AuthExpiredError, ScraperError
from ..models import JobItem, parse_salary
from ..paths import ROOT
from ..registry import register
from .base import BaseScraper

SEARCH_URL = "https://www.zhipin.com/web/geek/job?query={key}&city={code}"
ROUTE_GLOB = "**/wapi/zpgeek/search/joblist.json*"
DEFAULT_PROFILE = "data/browser_profile_chrome"
DEBUG_PORT = 9333


@register
class ZhipinScraper(BaseScraper):
    platform = "zhipin"
    city_codes = {"上海": "101020100"}

    def start(self, engine) -> None:
        super().start(engine)
        # BOSS 慎重：重试次数压到 1 次
        if self.fetch.max_retries > 1:
            self.fetch = replace(self.fetch, max_retries=1)
        profile = self.settings.extra.get("profile_dir", DEFAULT_PROFILE)
        profile_dir = Path(profile)
        if not profile_dir.is_absolute():
            profile_dir = ROOT / profile_dir
        ctx = engine.attach_real_chrome(profile_dir, port=DEBUG_PORT)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        self._pages.append(page)

    def finish(self) -> None:
        # 上下文属于真实 Chrome（引擎管理生命周期），这里只放手引用
        self._pages.clear()

    def search(self, keyword: str, city: str) -> Iterator[JobItem]:
        code = self.city_code(city, default="")
        if not code:
            self.log.warning("未知城市「%s」无城市码，按上海（101020100）抓取", city)
            code = "101020100"
        url = SEARCH_URL.format(key=quote(keyword), code=code)
        data = self.fetch_api_json_routed(url, ROUTE_GLOB)
        api_code = data.get("code")
        if api_code == 37:
            raise AuthExpiredError(
                "BOSS 登录态失效或触发安全验证：请运行 scripts/login_zhipin.py 重新登录")
        if api_code != 0:
            raise ScraperError(
                f"BOSS 接口异常：code={api_code} message={data.get('message')}")
        for j in (data.get("zpData") or {}).get("jobList") or []:
            item = self._parse_job(j)
            if item is not None:
                yield item

    @staticmethod
    def _parse_job(j: dict) -> Optional[JobItem]:
        jid = str(j.get("encryptJobId") or "")
        title = j.get("jobName") or ""
        if not jid or not title:
            return None
        tags = list(j.get("skills") or []) + list(j.get("welfareList") or [])
        return JobItem(
            platform="zhipin",
            site_job_id=jid,
            title=title,
            url=f"https://www.zhipin.com/job_detail/{jid}.html",
            company=j.get("brandName") or "",
            city=j.get("cityName") or "",
            district=j.get("areaDistrict") or j.get("businessDistrict") or "",
            salary_text=j.get("salaryDesc") or "",
            salary=parse_salary(j.get("salaryDesc")),
            experience=j.get("jobExperience") or "",
            education=j.get("jobDegree") or "",
            company_industry=j.get("brandIndustry") or "",
            company_size=j.get("brandScaleName") or "",
            hr_name=j.get("bossName") or "",
            tags=tags,
            publish_time_text="",   # 列表接口不含发布时间
        )
