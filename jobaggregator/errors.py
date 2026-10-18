"""异常体系（独立模块，避免循环导入）。"""

from __future__ import annotations


class ScraperError(Exception):
    """抓取过程出现无法继续的错误（网络、页面改版、解析失败等）。"""


class AuthExpiredError(ScraperError):
    """登录态失效或需要人工处理（验证码、重新登录）。

    pipeline 捕获后会把该平台标记为 auth_failed 并跳过该平台剩余关键词，
    其他平台不受影响；UI 顶部显示黄色横幅提示运行对应登录脚本。
    """
