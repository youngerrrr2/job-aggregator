"""config.yaml → 类型化配置对象（中文报错）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(Exception):
    """配置文件错误（信息为中文，直接展示给用户）。"""


@dataclass
class KeywordGroup:
    name: str
    job_type: str  # 全职 | 实习
    keywords: list[str]


@dataclass
class PlatformSettings:
    name: str
    enabled: bool = True
    max_pages_per_keyword: int = 1
    extra: dict = field(default_factory=dict)  # profile_dir / cookie_file 等

    def __post_init__(self) -> None:
        if self.max_pages_per_keyword < 1:
            self.max_pages_per_keyword = 1


@dataclass
class FetchSettings:
    headless: bool = False
    request_interval_sec: tuple[float, float] = (4.0, 8.0)   # 相邻关键词之间
    page_interval_sec: tuple[float, float] = (6.0, 12.0)     # 翻页之间（预留）
    timeout_sec: int = 25
    max_retries: int = 2
    archive_after_misses: int = 7


@dataclass
class AppConfig:
    city: str
    keyword_groups: list[KeywordGroup]
    platforms: dict[str, PlatformSettings]
    fetch: FetchSettings
    ui: dict


def _as_range(v, name: str) -> tuple[float, float]:
    try:
        a, b = float(v[0]), float(v[1])
    except Exception:
        raise ConfigError(f"fetch.{name} 应为 [下限, 上限] 两个数字，当前是：{v!r}")
    return (min(a, b), max(a, b))


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"找不到配置文件 {p}（应在项目根目录运行，或用 --config 指定路径）")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"config.yaml 格式错误：{e}")
    if not isinstance(raw, dict):
        raise ConfigError("config.yaml 顶层应为键值结构")

    city = raw.get("city")
    if not city or not isinstance(city, str):
        raise ConfigError("缺少 city（城市），例如：city: 上海")

    groups_raw = raw.get("keyword_groups") or []
    if not groups_raw:
        raise ConfigError("keyword_groups 为空——至少要有一组关键词")
    groups = []
    for i, g in enumerate(groups_raw, 1):
        name = g.get("name")
        kws = g.get("keywords") or []
        if not name or not kws:
            raise ConfigError(f"第 {i} 组关键词缺少 name 或 keywords")
        groups.append(
            KeywordGroup(name=str(name), job_type=str(g.get("job_type", "全职")),
                         keywords=[str(k) for k in kws])
        )

    platforms_raw = raw.get("platforms") or {}
    if not platforms_raw:
        raise ConfigError("platforms 为空——至少启用一个平台")
    known_extras = {"cookie_file", "profile_dir", "max_pages_per_keyword", "enabled"}
    platforms = {}
    for name, pcfg in platforms_raw.items():
        pcfg = pcfg or {}
        extra = {k: v for k, v in pcfg.items() if k not in known_extras}
        platforms[name] = PlatformSettings(
            name=name,
            enabled=bool(pcfg.get("enabled", True)),
            max_pages_per_keyword=int(pcfg.get("max_pages_per_keyword", 1)),
            extra=extra,
        )

    fraw = raw.get("fetch") or {}
    fetch = FetchSettings(
        headless=bool(fraw.get("headless", False)),
        request_interval_sec=_as_range(fraw.get("request_interval_sec", [4.0, 8.0]),
                                       "request_interval_sec"),
        page_interval_sec=_as_range(fraw.get("page_interval_sec", [6.0, 12.0]),
                                    "page_interval_sec"),
        timeout_sec=int(fraw.get("timeout_sec", 25)),
        max_retries=int(fraw.get("max_retries", 2)),
        archive_after_misses=int(fraw.get("archive_after_misses", 7)),
    )

    ui = raw.get("ui") or {"default_fresh_days": 14, "page_size": 100}
    return AppConfig(city=city, keyword_groups=groups, platforms=platforms,
                     fetch=fetch, ui=ui)
