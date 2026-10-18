"""数据模型与薪资解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SalaryRange:
    """统一折算后的月薪区间，单位：千元/月（K）。

    months 为年薪结构中的月数（"15-25K·13薪" → months=13），仅作展示参考。
    """

    min_k: float
    max_k: float
    months: int = 12


@dataclass
class JobItem:
    """一条岗位记录（与 jobs 表字段一一对应，raw 不入库）。"""

    platform: str
    site_job_id: str
    title: str
    url: str
    company: str = ""
    city: str = ""
    district: str = ""
    salary_text: str = ""          # 原始薪资文本，展示用
    salary: SalaryRange | None = None
    experience: str = ""
    education: str = ""
    company_industry: str = ""
    company_size: str = ""
    hr_name: str = ""
    tags: list[str] = field(default_factory=list)
    publish_time_text: str = ""
    raw: dict = field(default_factory=dict)  # 调试用原始数据，不写库

    @property
    def dedup_key(self) -> str:
        """去重主键：平台:站内岗位ID（URL 带随机参数不可靠）。"""
        return f"{self.platform}:{self.site_job_id}"


_NUM = r"(\d+(?:\.\d+)?)"


def _mk(a: float, b: float | None, months) -> SalaryRange:
    a = float(a)
    b = float(b) if b is not None else a
    if b < a:
        a, b = b, a
    months = int(months) if months else 12
    return SalaryRange(min_k=round(a, 1), max_k=round(b, 1), months=months)


def parse_salary(text: str | None) -> SalaryRange | None:
    """把各平台薪资文本统一折算为月薪千元（K/月）。

    支持："15-25K" "15-25K·13薪" "8-12k" "1.5-2万/月" "2-3万·15薪"
          "20-40万/年" "25-35万年薪" "300元/天" "3000-5000元/月" "2万"
    面议/¥---- → None
    """
    if not text:
        return None
    t = text.strip()
    if any(x in t for x in ("面议", "面谈", "----", "****", "薪资待定")):
        return None

    # 混合单位区间（须在普通区间之前）：8千-1.6万 / 8K-1.5万
    m = re.search(rf"{_NUM}\s*[Kk千]\s*[-–~到]\s*{_NUM}\s*万", t)
    if m:
        return _mk(m.group(1), float(m.group(2)) * 10, None)
    m = re.search(rf"{_NUM}\s*万\s*[-–~到]\s*{_NUM}\s*万", t)
    if m:
        a, b = float(m.group(1)) * 10, float(m.group(2)) * 10
        if "年薪" in t or "/年" in t:
            return _mk(a / 12, b / 12, None)
        return _mk(a, b, None)

    # 15K-25K / 15K~25K
    m = re.search(rf"{_NUM}\s*[Kk千]\s*[-–~到]\s*{_NUM}\s*[Kk千]?", t)
    if m:
        return _mk(m.group(1), m.group(2), None)

    # 15-25K / 15-25K·13薪 / 8-12k
    m = re.search(rf"{_NUM}(?:\s*[-–~到]\s*{_NUM})?\s*[Kk千](?:\s*·\s*(\d+)\s*薪)?", t)
    if m:
        return _mk(m.group(1), m.group(2), m.group(3))

    # 1.5-2万/月 · 20-40万/年 · 25-35万年薪 · 2-3万·15薪 · 2万
    m = re.search(rf"{_NUM}(?:\s*[-–~到]\s*{_NUM})?\s*万(?:\s*/\s*(月|年))?(?:\s*·\s*(\d+)\s*薪)?", t)
    if m:
        a, b, unit, months = m.group(1), m.group(2), m.group(3), m.group(4)
        if unit == "年" or "年薪" in t or "/年" in t:
            # 万/年 → 月薪K = 万*10/12
            return _mk(float(a) * 10 / 12, float(b) * 10 / 12 if b else None, months)
        return _mk(float(a) * 10, float(b) * 10 if b else None, months)

    # 300元/天（按每月 21.75 个工作日折算）
    m = re.search(rf"{_NUM}\s*元\s*/\s*天", t)
    if m:
        return _mk(float(m.group(1)) * 21.75 / 1000, None, None)

    # 3000-5000元/月
    m = re.search(rf"{_NUM}(?:\s*[-–~到]\s*{_NUM})?\s*元\s*/\s*月", t)
    if m:
        return _mk(float(m.group(1)) / 1000, float(m.group(2)) / 1000 if m.group(2) else None, None)

    # 8000-11000元（无 /月 后缀，默认月薪；智联 salary60 格式）
    m = re.search(rf"{_NUM}(?:\s*[-–~到]\s*{_NUM})?\s*元", t)
    if m:
        return _mk(float(m.group(1)) / 1000, float(m.group(2)) / 1000 if m.group(2) else None, None)

    return None
