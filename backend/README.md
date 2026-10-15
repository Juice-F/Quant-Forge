# 后端

## 启动策略展示服务

在仓库根目录执行：

```powershell
.\scripts\dev.ps1
```

也可以在当前目录直接执行：

```powershell
uv run python main.py
```

## 数据同步

`main.py` 启动 FastAPI 服务，默认监听 `127.0.0.1:8000`，接口文档位于 `/docs`，不通过命令执行策略。前端开发服务将 `/api` 请求代理到该端口。市场数据采集和存储位于 `market_data/`，`market_data/api.py` 提供手工测试用的行情同步工具接口，每项同步逻辑对应一个独立的 `sync_*` 函数。

数据源默认是 `tushare`，不支持 `auto` 或自动切换。目前 Tushare 同步接口尚未实现，默认调用会明确报错。现阶段使用免费的 BaoStock 测试时，必须显式传入 `source="baostock"`；日线和复权因子同步须指定 `start_date` 和 `end_date`。

复权因子和日线同步接受 `symbols`，传入股票列表时无需先同步 metadata，不传时从 `stock.parquet` 读取全量股票。`row_store.py` 仅保留 `save_adjust_factor()` 和 `save_daily_k_line()` 两个保存方法。保存格式沿用现有逻辑，重复运行按股票和日期去重；同步方法返回成功数、失败数、行数和失败详情。

### 手工调用行情工具

启动后访问 `http://127.0.0.1:8000/docs`，展开“行情工具（手工测试）”，点击对应接口的 **Try it out**，填写 JSON 后执行。这些接口直接同步并保存本地数据，不需要前端页面。

| 方法 | 路径 | 用途 | 请求参数 |
| --- | --- | --- | --- |
| POST | `/api/tools/market-data/sync/trade-dates` | 交易日历 | `source`、可选起止日期 |
| POST | `/api/tools/market-data/sync/stock-basic` | 证券基础资料 | `source` |
| POST | `/api/tools/market-data/sync/adjust-factor` | 复权因子 | `source`、必填起止日期、可选 `symbols` |
| POST | `/api/tools/market-data/sync/daily-k-line` | 未复权日线 | `source`、必填起止日期、可选 `symbols` |

例如，测试日线或复权因子同步时填写：

```json
{
  "source": "baostock",
  "start_date": "2026-07-13",
  "end_date": "2026-10-13",
  "symbols": ["sh.600519"]
}
```

交易日历的日期不传时，默认从 2000-01-01 同步到北京时间当年年末。基础资料请求可填写 `{"source": "baostock"}`。错误或缺失参数返回 422，尚未实现的 Tushare 同步返回 501，缺少本地基础资料等运行错误返回 400。逐股票同步的部分失败仍以成功响应返回，通过 `failed_count` 和 `failures` 查看详情。

请求会等待同步完成后返回；日线和复权因子仍按每次请求前等待 5 秒的规则执行，因此全量同步可能耗时较长。省略 `symbols` 前需先同步基础资料；显式传入时不能为空列表，代码格式为 `sh.600519`、`sz.000333` 等。

基础资料 metadata 已完成同步。BaoStock 的 `query_stock_basic()` 返回多种证券类型，`type` 包括股票、指数、其他、可转债和 ETF，统一写入 `stock.parquet`。

## 代码格式化

在当前目录执行：

```powershell
uv run --group dev isort .
uv run --group dev black .
```

数据 provider 使用 BaoStock 获取基础资料 metadata。BaoStock 使用 `query_stock_basic()` 获取包含 ETF 的证券基础列表，并保留接口的原始字段。BaoStock provider 通过通用的 `connect()` 生命周期方法建立匿名会话，底层调用 BaoStock SDK 的 `bs.login()`；这里不涉及用户名、密码、Token 或 API Key。metadata 行中会写入 `source` 和北京时间格式的 `ingest_time`。

metadata 可通过上述接口同步，也可从 `market_data.api` 导入 `sync_stock_basic`、`sync_trade_dates` 等函数直接调用。默认数据目录是系统用户目录下的 `.a-stock-data`，也可以用 `A_STOCK_DATA_ROOT` 覆盖。

交易日历已经按年份保存到 `{source}/metadata/trade_dates/<年份>.parquet`。证券基础资料按数据类型保存到 `{source}/metadata/stock_basic/stock.parquet`、`index.parquet` 和 `fund.parquet`，并按同步日期保存快照。

复权事件通过对应 provider 的 `fetch_adjust_factor()` 获取，并由 `market_data.api.sync_adjust_factor()` 写入 `{source}/row/adjust_factor/<股票代码>.parquet`；每只股票一个文件，使用 `code` 和 `dividOperateDate` 去重。

日线行情通过 `market_data.api.sync_daily_k_line()` 同步，写入 `{source}/row/k_line/<股票代码>.parquet`，每只股票一个文件，按 `code` 和 `trade_date` 去重。复权因子和日线均跨年份合并保存，重复同步更新同一文件。交易日历仍按年份保存。

复权因子和原始日线均按股票列表逐只采集和保存，每次请求前等待 5 秒，重新登录后的重试请求也一样。日期是否齐全及开始日期是否晚于结束日期由接口参数模型和 `sync_*` 检查。每次运行都重新请求整个股票列表，不读写进度文件。

当前已支持交易日历、证券基础资料、复权因子和未复权日线行情同步。日线行情字段以 `code`、`trade_date`、OHLC 为核心，并保留成交量、成交额和换手率（数据源提供时）。

## 目录与职责

```text
backend/
├── market_data/      # 行情采集、存储、读取与复权
├── factor_engine/    # 按价值、质量、成长、动量、风险、规模和流动性分类的因子计算
├── strategies/       # 每个策略独立定义、参数、股票池与筛选逻辑
│   ├── momentum/     # 动量
│   ├── mean_reversion/ # 均值回归
│   └── low_volatility/ # 低波动
├── tests/            # 按模块和策略目录组织测试
└── main.py           # 策略展示与参数预览 HTTP 服务
```

`factor_engine` 保留全部已有计算能力。各策略独立拥有 `definition.py`（默认参数、筛选定义、结果模型及股票和指数范围）、`strategy.py`（参数校验、展示信息与入口）和 `screening.py`（筛选计算）。回测也由各策略自己的 `backtest.py` 定义，不设置顶层公共回测目录；目前仅动量策略实现了周调仓研究回测。各级 `__init__.py` 只保留包说明，不定义或导出模块。

## 策略展示与参数

因子目录结构、已有能力、计算口径及导入路径见 [factor_engine/docs.md](factor_engine/docs.md)。

行情读取与复权位于 `market_data/adjustment.py`；各策略在自己的 `screening.py` 中读取行情、调用因子函数、预热窗口并汇总结果，不设置公共指标汇总模块。

每个策略统一通过 `run(values, *, preview=False)` 校验参数、组装筛选定义并执行筛选。FastAPI 展示与预览接口传入 `preview=True`，只返回展示信息、参数 JSON Schema、筛选定义和股票池，不读取行情或执行筛选。前端根据参数定义显示选择框、日期和阈值输入，并调用预览接口校验入参。无效参数返回 HTTP 422，未知策略返回 HTTP 404。预览不修改默认参数；参数只在当前页面有效。

展示接口：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/strategies` | 三个策略的展示信息 |
| GET | `/api/strategies/{id}` | 单个策略详情与默认参数 |
| POST | `/api/strategies/{id}/preview` | JSON 参数校验和规则预览 |
| POST | `/api/strategies/momentum/backtest` | 动量周调仓研究回测，返回指标、净值、决策与交易记录 |

策略 ID 为 `momentum`、`mean_reversion`、`low_volatility`。三个策略分别支持最低收益与 MA20 偏离、最高 MA20 偏离、最高波动率与回撤阈值。通用可选参数包括起止日期、数据源、复权方式和基准指数。比例 `0.15` 表示 15%。默认日期为历史示例，不自动切换到最新行情。各目录的 `strategy.run(values)` 保留独立筛选实现；动量回测使用下面单独定义的滚动规则，不使用整个回测区间的收益选股。

在仓库根目录也可执行 `scripts/dev.ps1`；通过 `-Port` 调整端口：

```powershell
.\scripts\dev.ps1 -Port 8000
```

股票池为各策略目录 `definition.py` 中的 `STOCK_NAMES`，指数仅作为基准。支持区间收益、最大回撤、区间日收益波动率、MA20／MA60 偏离、末日成交量比和超额收益，条件通过 `gte` / `lte` 按 AND 组合。超额收益 `0.05` 表示 5 个百分点，成交量比 `1` 表示一倍。

均线使用截至结束日期的历史数据预热，区间收益、回撤和波动率只使用所选区间，波动率不年化且不包含首日对区间前一天的收益。指标不足返回 `null`，不会通过依赖该指标的条件；空值排序放最后。基准须覆盖股票实际区间的起止日才能计算超额收益。每只股票返回实际日期、因子值、条件实际值和阈值。

## 验证

```powershell
uv run --group dev pytest
uv run --group dev isort .
uv run --group dev black .
```

测试结构与职责见 [tests/README.md](tests/README.md)。本地服务用于开发；前端生产部署需配置页面路由回退到 `index.html`，并将 `/api` 代理到后端服务。

## 动量周调仓回测

实现位于 [strategies/momentum/backtest.py](strategies/momentum/backtest.py)，只读取本地 BaoStock 行情，不自动同步，也不保存服务器端任务。前端回测页尚未接入此接口。

### 交易规则

- 股票池沿用动量策略配置的五只股票；默认本金 10 万元。
- 近 `lookback` 个交易日收益（默认 20 日）严格大于零，且收盘价不低于 MA20，按动量降序选前 `top_n` 只（默认 3 只）。动量相同时按代码排序。
- 每个自然周首个交易日开盘调仓，所有信号使用上一交易日收盘及更早数据。节假日以本地沪深300交易日期为准；区间从该范围内首次周调仓日开始。
- 每只入选股票目标占总资产的 `1 / top_n`，不足的名额留现金；落选清仓，保留股票也调整到目标权重。先卖后买，买入金额按可用现金缩减，不借款。
- 成交价采用后复权开盘价加减滑点，日末按后复权收盘价估值。期末不强制清仓，因此未计期末卖出费用。
- 默认双向佣金 0.03%、双向滑点 0.05%、卖出附加费用 0.05%。这些是固定研究假设，不代表历史真实税费，不含最低佣金。
- 无有效成交量时取消该次订单，持仓保留到下一次调仓；成交量空值按不可成交处理，结果包含每只股票缺失天数。缺价格或区间覆盖不足直接报错，不静默删除交易日。

### 对照与指标

所有组合采用同一本金、同一起止交易日和费用假设：

| 结果键 | 对照 |
| --- | --- |
| `momentum_weekly` | 动量选股，每周调仓 |
| `universe_hold` | 五股初始等额买入，此后持有 |
| `universe_weekly` | 五股每周恢复等权，不做动量筛选 |
| `initial_momentum_hold` | 仅首次动量选股，此后持有，保留未填满名额的现金 |
| `benchmark` | 沪深300价格指数，按首日开盘起算，不含分红与费用 |
| `cash` | 零利息现金 |

输出总收益、期末资产、年化收益、最大回撤、年化波动率和夏普。年化使用每年 252 个交易日；夏普使用零无风险收益，波动为零时返回 `null`。最大回撤包含初始本金至首日的损失。`strategy_excess_return` 为动量周调仓总收益减该对照总收益，单位为比例，例如 `0.10` 表示 10 个百分点。

四个股票组合还输出成交笔数、决策次数、费用、滑点金额、平均仓位，以及累计成交金额除初始本金的换手倍数（双向累计，不年化）。完整返回含每日资产、每周决策、交易和取消订单。
