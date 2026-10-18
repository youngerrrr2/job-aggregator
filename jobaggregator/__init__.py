"""job-aggregator：个人本地财务岗位聚合平台（仅自用）。

结构：
- config.py    YAML 配置加载与校验
- models.py    JobItem / SalaryRange / parse_salary()
- db.py        SQLite 存储（WAL，支持 UI 读 + 抓取写并行）
- browser.py   Playwright 浏览器引擎（Chrome→Edge→Chromium 回退）
- registry.py  @register 装饰器 + scrapers 自动发现（插件机制）
- pipeline.py  编排：逐平台 → 逐关键词 → 入库 → fetch_runs 记录
- scrapers/    各平台抓取插件（base.py 定义接口）
"""

__version__ = "0.1.0"
