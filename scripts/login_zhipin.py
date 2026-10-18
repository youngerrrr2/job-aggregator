"""BOSS直聘手动登录一次（本人操作，脚本不碰任何账号信息）。

方式：直接启动本机真实 Chrome（独立数据目录，与日常浏览器完全隔离），
Playwright 仅通过调试端口「附加读取」，浏览器本身 100% 真实——
BOSS 对 Playwright 启动的浏览器会白屏，这是可行路径。

流程：弹出真实 Chrome 并打开登录页 → 你本人登录 → 回控制台按回车 →
登录态留在 data/browser_profile_chrome/，以后抓取自动复用。

用法：python scripts/login_zhipin.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
PROFILE_DIR = ROOT / "data" / "browser_profile_chrome"
DEBUG_PORT = 9333
FLAG_FILE = ROOT / "data" / "zhipin_login.flag"


def _chrome_path() -> str:
    for p in CHROME_CANDIDATES:
        if Path(p).exists():
            return p
    raise SystemExit("找不到 chrome.exe，请把路径加到脚本顶部 CHROME_CANDIDATES")


def main() -> int:
    chrome = _chrome_path()
    print("=" * 52)
    print("即将打开【真实 Chrome】→ 请你本人完成 BOSS直聘登录")
    print("（独立浏览器目录，与你的日常 Chrome 互不影响）")
    print("登录成功（能看到头像/昵称）后，回到本窗口按回车保存")
    print("=" * 52)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([
        chrome,
        f"--user-data-dir={PROFILE_DIR}",
        f"--remote-debugging-port={DEBUG_PORT}",
        "--no-first-run", "--no-default-browser-check",
        "--window-size=1440,900",
        "https://login.zhipin.com/",
    ])
    time.sleep(6)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEBUG_PORT}")
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            html = page.content()
            (ROOT / "data" / "captures" / "zhipin_login_diag.txt").write_text(
                f"url={page.url}\ntitle={page.title()}\nhtml_len={len(html)}\n"
                f"head={html[:400]}\n", encoding="utf-8")
            print(f"\n页面状态：{page.url[:60]}（长度 {len(html)}）")
        except Exception as e:
            print(f"\n读取页面失败：{e!r}")
        try:
            input("\n…等你登录。完成后按回车（Enter）保存登录态：")
        except EOFError:
            pass
        names = sorted({c["name"] for c in ctx.cookies()})
        FLAG_FILE.parent.mkdir(parents=True, exist_ok=True)
        FLAG_FILE.write_text(
            f"logged_in_at={datetime.now().isoformat(timespec='seconds')}\n"
            f"cookies={','.join(names)}\n", encoding="utf-8")
        browser.close()   # 仅断开读取连接，Chrome 留给你自己关
    print(f"\n登录态已保存在 {PROFILE_DIR}")
    print("（浏览器窗口你可以直接关掉）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
