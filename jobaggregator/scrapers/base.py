"""抓取插件抽象基类。

生命周期：start(engine) → search(关键词)...（每个关键词一次）→ finish()
start() 里按需创建本平台的浏览器页面/上下文，finish() 里清理。
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Callable, ClassVar, Iterator, Optional

from ..browser import BrowserEngine
from ..config import FetchSettings, PlatformSettings
from ..errors import ScraperError
from ..models import JobItem


class BaseScraper(ABC):
    platform: ClassVar[str] = ""          # "liepin" | "job51" | "zhaopin" | "zhipin"
    city_codes: ClassVar[dict[str, str]] = {}  # 中文城市名 → 本平台城市码

    def __init__(self, settings: PlatformSettings,
                 fetch: Optional[FetchSettings] = None) -> None:
        self.settings = settings
        self.fetch = fetch or FetchSettings()
        self.log = logging.getLogger(f"jobaggregator.scrapers.{self.platform or 'base'}")
        self.engine: BrowserEngine | None = None
        self._pages: list = []          # start() 中创建的页面，finish() 统一关

    # ---------- 生命周期 ----------

    def start(self, engine: BrowserEngine) -> None:
        """每平台一次：拿引擎引用（子类可覆盖，在此建页面/上下文）。"""
        self.engine = engine

    def finish(self) -> None:
        """每平台一次：清理本平台资源（连上下文一起关，不占内存）。"""
        for p in self._pages:
            try:
                p.context.close()
            except Exception:
                pass
        self._pages.clear()

    # ---------- 抓取 ----------

    @abstractmethod
    def search(self, keyword: str, city: str) -> Iterator[JobItem]:
        """抓取一个关键词的岗位列表（city 为中文城市名，如「上海」）。"""

    # ---------- 工具 ----------

    def city_code(self, city: str, default: str = "") -> str:
        return self.city_codes.get(city, default)

    def _capture(self, url: str, pred, what: str):
        """打开页面并捕获首个满足 pred 的响应，失败整页重载重试。"""
        if not self._pages:
            raise ScraperError(f"[{self.platform}] 页面未初始化（start 未创建）")
        page = self._pages[0]
        timeout_ms = self.fetch.timeout_sec * 1000
        last_err: Exception | None = None
        for attempt in range(max(1, self.fetch.max_retries) + 1):
            try:
                with page.expect_response(pred, timeout=timeout_ms) as info:
                    page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                return info.value
            except Exception as e:
                last_err = e
                self.log.warning("[%s] 页面/接口第 %d 次加载失败：%r",
                                 self.platform, attempt + 1, e)
        raise ScraperError(
            f"[{self.platform}] 打开页面或捕获{what}失败：{last_err!r}")

    @staticmethod
    def _url_pred(api_mark: str, match: Optional[Callable] = None):
        def pred(r) -> bool:
            if api_mark not in r.url or r.status != 200:
                return False
            return True if match is None else bool(match(r))
        return pred

    def fetch_api_json(self, url: str, api_mark: str,
                       match: Optional[Callable] = None) -> dict:
        """打开页面并捕获网站自己发出的匹配接口响应，返回其 JSON。

        页面在整个平台生命周期内复用（Cookie/挑战结果保留，减少风控触发）。
        match(response) 用于同一接口一次加载被请求多次时挑出目标那次
        （如猎聘先发一个返回空结果的表单请求，再发真正的 JSON POST）。
        """
        resp = self._capture(url, self._url_pred(api_mark, match), "接口")
        data = resp.json()
        if not isinstance(data, dict):
            raise ScraperError(f"[{self.platform}] 接口响应不是 JSON 对象")
        return data

    def fetch_page_text(self, url: str, mark: str,
                        match: Optional[Callable] = None) -> str:
        """打开页面并捕获文档响应，返回其 HTML（SSR 数据嵌在文档里的站点用）。

        match 默认要求该响应是导航请求（主文档而非子资源）。
        """
        if match is None:
            match = lambda r: r.request.is_navigation_request()  # noqa: E731
        resp = self._capture(url, self._url_pred(mark, match), "页面文档")
        return resp.text()

    def fetch_api_json_routed(self, url: str, glob: str) -> dict:
        """打开页面并透传捕获接口响应（BOSS 这类「加载后自我跳转」的站点用）。

        expect_response 在页面自我跳转后读不到响应体（No resource with
        given identifier），路由透传则由我们代发同样签名/Cookie 的请求，
        拿到响应体后原样交还页面——对站点而言请求完全一致。
        """
        if not self._pages:
            raise ScraperError(f"[{self.platform}] 页面未初始化（start 未创建）")
        page = self._pages[0]
        timeout_ms = self.fetch.timeout_sec * 1000
        holder: dict = {}

        def handler(route):
            resp = route.fetch()
            holder["status"] = resp.status
            holder["body"] = resp.text()
            route.fulfill(response=resp)

        page.route(glob, handler)
        try:
            last_err: Exception | None = None
            for attempt in range(max(1, self.fetch.max_retries) + 1):
                holder.clear()
                try:
                    page.goto(url, timeout=timeout_ms,
                              wait_until="domcontentloaded")
                    deadline = time.monotonic() + self.fetch.timeout_sec
                    while time.monotonic() < deadline and "body" not in holder:
                        page.wait_for_timeout(300)
                    if "body" not in holder:
                        raise TimeoutError("路由未捕获到接口响应")
                    data = json.loads(holder["body"])
                    if not isinstance(data, dict):
                        raise ScraperError(
                            f"[{self.platform}] 接口响应不是 JSON 对象")
                    return data
                except ScraperError:
                    raise
                except Exception as e:
                    last_err = e
                    self.log.warning("[%s] 页面/接口第 %d 次加载失败：%r",
                                     self.platform, attempt + 1, e)
            raise ScraperError(
                f"[{self.platform}] 打开页面或路由捕获接口失败：{last_err!r}")
        finally:
            try:
                page.unroute(glob, handler)
            except Exception:
                pass
