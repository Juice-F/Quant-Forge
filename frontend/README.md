# 量化研究工作台

React + TypeScript + Vite + shadcn/ui + Tailwind CSS。页面分为因子、策略与回测三个入口。

## 启动

先在仓库根目录运行后端展示服务：

```powershell
.\scripts\dev.ps1
```

再在 `frontend/` 运行：

```powershell
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`。Vite 将 `/api` 请求代理到 `http://127.0.0.1:8000`；后端端口变更时需同步修改 `vite.config.ts`。

## 页面与路由

| 路由 | 页面 |
| --- | --- |
| `/` | 跳转到策略列表 |
| `/factors` | 现有因子目录 |
| `/factors/:factorId` | 因子公式、单位和计算口径 |
| `/strategies` | 后端导出的三个策略 |
| `/strategies/:strategyId` | 策略说明、可选参数与筛选规则 |
| `/backtests` | 回测待实现状态 |
| `/backtests/:backtestId` | 预留详情路由，目前提示没有记录 |

列表和详情支持直接访问、刷新及浏览器前进后退。生产部署时需将页面路径回退到 `index.html`，并配置 `/api` 代理。

## 参数选择

策略将因子组合为选股条件，并指定入选股票的排序方式。策略列表与详情页说明其用途和当前支持的功能，不展示股票池及股票数量。后续计划支持全量股票筛选；目前后端筛选范围仍由各策略的 `definition.py` 中的 `STOCK_NAMES` 定义。

进入策略详情后，可选择日期、数据源、复权方式、基准指数和该策略的阈值。点击“校验并预览规则”调用后端参数校验，更新筛选逻辑展示。比例 `0.05` 表示 5%，默认日期是历史示例。

参数调整仅用于当前页面预览，不修改策略默认参数。页面不执行策略，不要求命令行运行策略或导入结果文件。动量策略已在后端实现独立的周调仓研究回测（`POST /api/strategies/momentum/backtest`），规则和调用见 [后端说明](../backend/README.md#动量周调仓回测)。前端回测页尚未接入，没有模拟收益或交易记录。

## 构建

```powershell
npm run build
```
