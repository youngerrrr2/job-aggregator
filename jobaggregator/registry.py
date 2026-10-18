"""插件注册：@register 装饰器 + scrapers 包自动发现。"""

from __future__ import annotations

import importlib
import pkgutil

SCRAPERS: dict[str, type] = {}


def register(cls):
    """类装饰器：@register 把平台抓取器登记到 SCRAPERS[platform]。"""
    if not getattr(cls, "platform", None):
        raise ValueError(f"{cls.__name__} 缺少 platform 类属性，无法注册")
    SCRAPERS[cls.platform] = cls
    return cls


def load_all() -> dict[str, type]:
    """导入 scrapers 包下全部模块触发注册，返回 {platform: 类}。"""
    from . import scrapers

    for m in pkgutil.iter_modules(scrapers.__path__):
        if m.name in ("base",):
            continue
        importlib.import_module(f"{scrapers.__name__}.{m.name}")
    return dict(SCRAPERS)
