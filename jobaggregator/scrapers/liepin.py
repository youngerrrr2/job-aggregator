"""猎聘抓取插件：浏览器打开搜索页，拦截它自己的搜索接口响应（免登录）。

接口探测记录（2026-10，scripts/capture_api.py 抓包）：
  页面 https://www.liepin.com/zhaopin/?key=…&dq=020
  会自行 POST api-c.liepin.com/api/com.liepin.searchfront4c.pc-search-job
  响应结构：data.data.jobCardList[]（注意双层 data！）
    job.{jobId,title,salary("8-12k"),dq("上海-浦东"),requireWorkYears,
         requireEduLevel,link,refreshTime("20261013110410"),labels}
    comp.{compName,compScale,compIndustry}
    recruiter.{recruiterName}

两个坑（2026-10-14 scripts/discover_liepin_dq.py / verify_liepin_dq.py 实测）：
  1. 每次页面加载先发一个表单编码的空请求（selectedDqCode=410，0 张卡），
     再发真正的 JSON POST（body 以 {"data" 开头）——必须只拦后者（match 谓词）。
  2. 城市过滤用 URL 参数 dq=码（上海=020），不是 city=；city=上海 会被塞进
     表单 city 字段但 dq 仍是 410（全国）。码表来自接口
     com.liepin.searchfront4c.pc-search-job-cond-init：410 全国 / 010 北京 /
     020 上海 / 030 天津 / 040 重庆（其余城市跑 discover_liepin_dq.py 查）。
改版后校准：python scripts/capture_api.py liepin
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Iterator, Optional
from urllib.parse import quote

from ..errors import ScraperError
from ..models import JobItem, parse_salary
from ..registry import register
from .base import BaseScraper

SEARCH_URL = "https://www.liepin.com/zhaopin/?key={key}&dq={dq}"
API_MARK = "com.liepin.searchfront4c.pc-search-job"


def _is_job_json_post(response) -> bool:
    """真数据那次请求：JSON POST（body 以 {"data" 开头）。"""
    post = response.request.post_data or ""
    return post.lstrip().startswith('{"data"')


@register
class LiepinScraper(BaseScraper):
    platform = "liepin"
    city_codes = {"上海": "020", "北京": "010", "天津": "030", "重庆": "040",
                  "全国": "410"}

    def start(self, engine) -> None:
        super().start(engine)
        self._pages.append(engine.fresh_page())

    def search(self, keyword: str, city: str) -> Iterator[JobItem]:
        dq = self.city_code(city, default="")
        if not dq:
            self.log.warning("未知城市「%s」无 dq 码，按全国（410）抓取", city)
            dq = "410"
        url = SEARCH_URL.format(key=quote(keyword), dq=dq)
        data = self.fetch_api_json(url, API_MARK, match=_is_job_json_post)
        if data.get("flag") != 1:
            raise ScraperError(
                f"猎聘接口返回异常：flag={data.get('flag')} "
                f"code={data.get('code')} msg={data.get('msg')}")
        cards = ((data.get("data") or {}).get("data") or {}).get("jobCardList") or []
        for card in cards:
            item = self._parse_card(card)
            if item is not None:
                yield item

    @staticmethod
    def _parse_card(card: dict) -> Optional[JobItem]:
        job = card.get("job") or {}
        comp = card.get("comp") or {}
        recruiter = card.get("recruiter") or {}
        jid = str(job.get("jobId") or "")
        title = job.get("title") or ""
        if not jid or not title:
            return None
        city_part, _, district = (job.get("dq") or "").partition("-")
        publish = _format_refresh(job.get("refreshTime"))
        return JobItem(
            platform="liepin",
            site_job_id=jid,
            title=title,
            url=job.get("link") or "",
            company=comp.get("compName") or "",
            city=city_part,
            district=district,
            salary_text=job.get("salary") or "",
            salary=parse_salary(job.get("salary")),
            experience=job.get("requireWorkYears") or "",
            education=job.get("requireEduLevel") or "",
            company_industry=comp.get("compIndustry") or "",
            company_size=comp.get("compScale") or "",
            hr_name=recruiter.get("recruiterName") or "",
            tags=list(job.get("labels") or []),
            publish_time_text=publish,
        )


def _format_refresh(raw: str) -> str:
    """refreshTime "20261013110410" → "2026-10-13 11:04"。"""
    if isinstance(raw, str) and re.fullmatch(r"\d{14}", raw):
        try:
            return datetime.strptime(raw, "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
    return raw or ""
