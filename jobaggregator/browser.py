"""Playwright 浏览器引擎。

探测结论（2026-10）：四大平台纯 requests 全被挑战页拦截，统一走真实浏览器。
- 启动渠道三级回退：系统 Chrome → 系统 Edge → Playwright 自带 Chromium
- 免登录平台：fresh_page() 每平台一个干净上下文
- BOSS：attach_real_chrome() —— 本机真实 Chrome（独立目录）+ CDP 附加读取；
  Playwright 启动的浏览器（含 persistent_context）会被 BOSS 风控探测后白屏，
  真实 Chrome 实测可过 _security_check（2026-10-14）。
"""

from __future__ import annotations

import logging
import socket
import subprocess
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

CHANNELS: list[Optional[str]] = ["chrome", "msedge", None]  # None = 自带 Chromium

REAL_CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


class BrowserEngine:
    """整个抓取进程共享一个引擎；上下文按平台隔离。"""

    def __init__(self, headless: bool = False) -> None:
        self._headless = headless
        self._pw = None
        self._browser: Optional[Browser] = None
        self._channel: Optional[str] = None
        self._contexts: list[BrowserContext] = []
        self._cdp_browsers: list[Browser] = []     # attach 的真实 Chrome
        self._chrome_proc: Optional[subprocess.Popen] = None  # 我们启动的 Chrome

    # ---------- 生命周期 ----------

    def __enter__(self) -> "BrowserEngine":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _ensure_browser(self) -> None:
        """按 chrome → msedge → chromium 顺序启动，成功一个即用。"""
        if self._browser is not None:
            return
        self._pw = sync_playwright().start()
        last_err: Exception | None = None
        for channel in CHANNELS:
            try:
                self._browser = self._pw.chromium.launch(
                    channel=channel, headless=self._headless
                )
                self._channel = channel
                log.info("浏览器引擎就绪（channel=%s, headless=%s）",
                         channel or "chromium", self._headless)
                return
            except Exception as e:
                last_err = e
                log.info("浏览器 channel=%s 不可用：%s", channel or "chromium", e)
        self._pw.stop()
        self._pw = None
        raise RuntimeError(f"Chrome / Edge / Chromium 均无法启动：{last_err!r}")

    def close(self) -> None:
        for ctx in self._contexts:
            try:
                ctx.close()
            except Exception:
                pass
        self._contexts.clear()
        for b in self._cdp_browsers:          # 只断开连接，不动浏览器进程
            try:
                b.close()
            except Exception:
                pass
        self._cdp_browsers.clear()
        if self._chrome_proc is not None:     # 我们启动的 Chrome 才结束
            try:
                self._chrome_proc.terminate()
            except Exception:
                pass
            self._chrome_proc = None
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None

    # ---------- 上下文 ----------

    def attach_real_chrome(self, user_data_dir: str | Path, port: int = 9333,
                           url: str | None = None) -> BrowserContext:
        """BOSS 用：启动/复用本机真实 Chrome（独立数据目录），CDP 附加读取。

        BOSS 风控会探测 Playwright 启动的浏览器（含 persistent_context）并白屏；
        真实 Chrome 实测可过 _security_check（2026-10-14）。
        端口已活则直接附加（如用户刚跑完 login_zhipin.py）；
        由本方法启动的 Chrome 在 close() 时一并结束，已有的不动。
        """
        def _port_alive() -> bool:
            with socket.socket() as s:
                s.settimeout(1.0)
                return s.connect_ex(("127.0.0.1", port)) == 0

        started_here = False
        if not _port_alive():
            chrome = next((p for p in REAL_CHROME_CANDIDATES if Path(p).exists()),
                          None)
            if chrome is None:
                raise RuntimeError("找不到本机 chrome.exe（真实 Chrome）")
            Path(user_data_dir).mkdir(parents=True, exist_ok=True)
            args = [chrome,
                    f"--user-data-dir={Path(user_data_dir).resolve()}",
                    f"--remote-debugging-port={port}",
                    "--no-first-run", "--no-default-browser-check",
                    "--window-size=1440,900"]
            if url:
                args.append(url)
            self._chrome_proc = subprocess.Popen(args)
            started_here = True
            for _ in range(30):
                if _port_alive():
                    break
                time.sleep(0.5)
            if not _port_alive():
                raise RuntimeError(f"真实 Chrome 调试端口 {port} 未就绪")
        if self._pw is None:
            self._pw = sync_playwright().start()
        browser = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        self._cdp_browsers.append(browser)
        if started_here:
            log.info("真实 Chrome 已启动（独立目录，端口 %d）", port)
        else:
            log.info("附加到已在运行的真实 Chrome（端口 %d）", port)
        return browser.contexts[0]

    def fresh_page(self) -> Page:
        """免登录平台用：干净上下文 + 真实 UA + zh-CN。"""
        self._ensure_browser()
        assert self._browser is not None
        ctx = self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            user_agent=UA,
        )
        self._contexts.append(ctx)
        return ctx.new_page()

    def persistent_context(self, user_data_dir: str | Path) -> BrowserContext:
        """BOSS 用：复用登录过的用户目录（真实指纹 + 登录态）。

        安全考虑（BOSS 风控最严）：
        - 不覆盖 UA —— 持久目录配本机真实 Chrome，UA 与指纹必须一致；
        - 不自报自动化身份（去掉 webdriver 标记 / --enable-automation），
          否则 BOSS 页面 JS 识别后直接白屏；
        - 渠道独立回退（chrome 优先）—— 不受临时上下文回退结果影响，
          避免「Chrome 建的目录被 Edge 打开」这种指纹突变。
        """
        if self._pw is None:
            self._pw = sync_playwright().start()
        Path(user_data_dir).mkdir(parents=True, exist_ok=True)
        last_err: Exception | None = None
        for channel in CHANNELS:
            try:
                ctx = self._pw.chromium.launch_persistent_context(
                    str(user_data_dir),
                    channel=channel,
                    headless=self._headless,
                    viewport={"width": 1440, "height": 900},
                    locale="zh-CN",
                    args=["--disable-blink-features=AutomationControlled"],
                    ignore_default_args=["--enable-automation"],
                )
                self._contexts.append(ctx)
                return ctx
            except Exception as e:
                last_err = e
        raise RuntimeError(f"持久上下文无法启动（chrome/edge/chromium）：{last_err!r}")
