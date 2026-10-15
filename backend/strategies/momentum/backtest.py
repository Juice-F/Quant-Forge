"""动量选股的周调仓研究回测，由策略 API 调用。"""

import math
from datetime import date
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from market_data.adjustment import get_adjusted_k_line, get_raw_k_line
from strategies.momentum.definition import STOCK_NAMES


def performance(equity: list[float], initial_capital: float) -> dict:
    values = pd.Series([initial_capital, *equity], dtype=float)
    returns = values.pct_change().iloc[1:]
    volatility = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    annual_return = (values.iloc[-1] / initial_capital) ** (252 / len(equity)) - 1
    return {
        "final_equity": float(values.iloc[-1]),
        "total_return": float(values.iloc[-1] / initial_capital - 1),
        "annual_return": float(annual_return),
        "max_drawdown": float((1 - values / values.cummax()).max()),
        "annual_volatility": volatility * math.sqrt(252),
        "sharpe": float(returns.mean() / volatility * math.sqrt(252)) if volatility > 1e-12 else None,
        "trading_days": len(equity),
    }


def simulate(
    frames: dict[str, pd.DataFrame],
    sessions: pd.DatetimeIndex,
    decisions: dict[pd.Timestamp, dict],
    initial_capital: float,
    commission: float,
    slippage: float,
    sell_fee: float,
) -> dict:
    """decisions 的权重是总资产占比；无法成交的订单取消，等待下次决策。"""
    cash = initial_capital
    positions = dict.fromkeys(frames, 0.0)
    daily, trades, rejected = [], [], []

    def blocked(symbol, day):
        bar = frames[symbol].loc[day]
        return bar["volume"] <= 0 or bar["open"] <= 0

    for day in sessions:
        opens = {symbol: float(frame.loc[day, "open"]) for symbol, frame in frames.items()}
        if day in decisions:
            decision = decisions[day]
            weights = decision["weights"]
            if (
                any(weight < 0 or not math.isfinite(weight) for weight in weights.values())
                or sum(weights.values()) > 1.00000001
            ):
                raise ValueError("目标权重必须非负且总和不超过 1。")
            equity = cash + sum(positions[symbol] * opens[symbol] for symbol in frames)
            targets = {symbol: equity * weights.get(symbol, 0) / opens[symbol] for symbol in frames}

            def execute(symbol, quantity, side):
                nonlocal cash
                price = opens[symbol] * (1 + slippage if side == "buy" else 1 - slippage)
                notional = quantity * price
                fee = notional * (commission + (sell_fee if side == "sell" else 0))
                if side == "buy":
                    positions[symbol] += quantity
                    cash -= notional + fee
                else:
                    positions[symbol] -= quantity
                    cash += notional - fee
                trades.append(
                    {
                        "date": day.date().isoformat(),
                        "signal_date": decision["signal_date"],
                        "symbol": symbol,
                        "side": side,
                        "adjusted_units": quantity,
                        "adjusted_price": price,
                        "notional": notional,
                        "fee": fee,
                        "slippage_cost": quantity * opens[symbol] * slippage,
                    }
                )

            # 先卖后买，当日新买入份额不会再卖出。
            for symbol in frames:
                difference = positions[symbol] - targets[symbol]
                if abs(difference * opens[symbol]) < 0.01:
                    continue
                if blocked(symbol, day):
                    rejected.append(
                        {"date": day.date().isoformat(), "symbol": symbol, "reason": "无有效成交量，取消本次订单"}
                    )
                elif difference > 0:
                    execute(symbol, difference, "sell")
            buys = {
                symbol: max(0, targets[symbol] - positions[symbol]) for symbol in frames if not blocked(symbol, day)
            }
            required = sum(
                quantity * opens[symbol] * (1 + slippage) * (1 + commission) for symbol, quantity in buys.items()
            )
            scale = min(1, max(0, cash) / required) if required else 0
            for symbol, quantity in buys.items():
                if quantity * scale * opens[symbol] >= 0.01:
                    execute(symbol, quantity * scale, "buy")
        equity = cash + sum(positions[symbol] * float(frames[symbol].loc[day, "close"]) for symbol in frames)
        if cash < -0.00001:
            raise ValueError("回测现金为负，资金约束失效。")
        daily.append({"date": day.date().isoformat(), "equity": equity, "cash": max(0, cash)})
    metrics = performance([item["equity"] for item in daily], initial_capital)
    metrics.update(
        {
            "trade_count": len(trades),
            "rebalance_count": len(decisions),
            "fees": sum(trade["fee"] for trade in trades),
            "slippage_cost": sum(trade["slippage_cost"] for trade in trades),
            "turnover": sum(trade["notional"] for trade in trades) / initial_capital,
            "average_exposure": sum(1 - item["cash"] / item["equity"] for item in daily) / len(daily),
        }
    )
    return {"metrics": metrics, "daily": daily, "trades": trades, "rejected_orders": rejected}


class Parameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date = date(2019, 1, 2)
    end_date: date = date(2026, 10, 13)
    initial_capital: float = Field(default=100000, gt=0, allow_inf_nan=False)
    lookback: int = Field(default=20, ge=2, le=250)
    top_n: int = Field(default=3, ge=1, le=len(STOCK_NAMES))
    commission: float = Field(default=0.0003, ge=0, le=0.02, allow_inf_nan=False)
    slippage: float = Field(default=0.0005, ge=0, le=0.02, allow_inf_nan=False)
    sell_fee: float = Field(default=0.0005, ge=0, le=0.02, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期。")
        return self


def weekly_decisions(frames: dict[str, pd.DataFrame], calendar: pd.DatetimeIndex, sessions, parameters) -> dict:
    """以基准交易日历识别自然周首日，信号窗口不包含成交日。"""
    decisions = {}
    scores = {}
    for symbol, frame in frames.items():
        close = frame["close"].reindex(calendar)
        scores[symbol] = pd.DataFrame(
            {
                "momentum": close / close.shift(parameters.lookback) - 1,
                "deviation": close / close.rolling(20).mean() - 1,
            }
        )
    for day in sessions:
        location = calendar.get_loc(day)
        if location == 0:
            raise ValueError("缺少回测开始前的信号数据。")
        previous = calendar[location - 1]
        if previous.isocalendar()[:2] == day.isocalendar()[:2]:
            continue
        candidates = []
        for symbol in frames:
            row = scores[symbol].loc[previous]
            window = frames[symbol].reindex(calendar).loc[:previous].tail(max(parameters.lookback + 1, 20))
            # 不使用过期收盘价填补信号；缺窗口或最近停牌的股票不入选。
            if len(window) < max(parameters.lookback + 1, 20) or window["close"].isna().any():
                continue
            if window.iloc[-1]["volume"] <= 0:
                continue
            if pd.notna(row["momentum"]) and row["momentum"] > 0 and row["deviation"] >= 0:
                candidates.append(
                    {"symbol": symbol, "momentum": float(row["momentum"]), "ma20_deviation": float(row["deviation"])}
                )
        candidates.sort(key=lambda item: (-item["momentum"], item["symbol"]))
        selected = candidates[: parameters.top_n]
        decisions[day] = {
            "signal_date": previous.date().isoformat(),
            "weights": {item["symbol"]: 1 / parameters.top_n for item in selected},
            "selected": selected,
        }
    return decisions


def run(values: dict | None = None, *, root: Path | None = None) -> dict:
    parameters = Parameters.model_validate(values or {})
    benchmark = get_raw_k_line("sh.000300", "baostock", end_date=parameters.end_date, root=root)
    benchmark.index = pd.DatetimeIndex(benchmark["trade_date"])
    calendar = benchmark.index
    if parameters.end_date > calendar[-1].date():
        raise ValueError(f"基准行情仅覆盖到 {calendar[-1].date()}，请先同步或缩短结束日期。")
    sessions = calendar[
        (calendar >= pd.Timestamp(parameters.start_date)) & (calendar <= pd.Timestamp(parameters.end_date))
    ]
    if len(sessions) < 2:
        raise ValueError("所选区间至少需要两个交易日。")
    if calendar.get_loc(sessions[0]) < max(parameters.lookback, 19):
        raise ValueError("开始日期之前缺少动量或 MA20 预热数据，请推迟开始日期或补齐行情。")
    frames = {}
    unavailable_volume = {}
    for symbol in STOCK_NAMES:
        frame = get_adjusted_k_line(symbol, "baostock", end_date=parameters.end_date, adjust_type="hfq", root=root)
        frame.index = pd.DatetimeIndex(frame["trade_date"])
        required = frame.reindex(sessions)
        for column in ("open", "close", "volume"):
            frame[column] = pd.to_numeric(frame[column], errors="raise")
            required[column] = pd.to_numeric(required[column], errors="raise")
        if required[["open", "close"]].isna().any().any():
            raise ValueError(f"{symbol} 未完整覆盖回测交易日，请补齐数据或调整区间。")
        if (
            not (required[["open", "close"]] > 0).all().all()
            or (required["volume"] < 0).any()
            or required["volume"].dropna().map(lambda value: not math.isfinite(value)).any()
        ):
            raise ValueError(f"{symbol} 含无效价格或成交量。")
        unavailable_volume[symbol] = int(required["volume"].isna().sum())
        frame["volume"] = frame["volume"].fillna(0)
        frames[symbol] = frame
    decisions = weekly_decisions(frames, calendar, sessions, parameters)
    if not decisions:
        raise ValueError("所选区间没有周调仓日，请扩大日期范围。")
    # 所有对照从首次可以执行周信号的同一天开始，避免不同入场日期。
    sessions = sessions[sessions >= min(decisions)]
    first_day = sessions[0]
    all_weights = {symbol: 1 / len(frames) for symbol in frames}
    weekly_equal = {day: {**decision, "weights": all_weights} for day, decision in decisions.items()}
    plans = {
        "momentum_weekly": decisions,
        "universe_hold": {first_day: {**decisions[first_day], "weights": all_weights}},
        "universe_weekly": weekly_equal,
        "initial_momentum_hold": {first_day: decisions[first_day]},
    }
    portfolios = {
        name: simulate(
            frames,
            sessions,
            plan,
            parameters.initial_capital,
            parameters.commission,
            parameters.slippage,
            parameters.sell_fee,
        )
        for name, plan in plans.items()
    }
    benchmark_values = [
        parameters.initial_capital * float(benchmark.loc[day, "close"] / benchmark.loc[first_day, "open"])
        for day in sessions
    ]
    portfolios["benchmark"] = {
        "metrics": performance(benchmark_values, parameters.initial_capital),
        "daily": [
            {"date": day.date().isoformat(), "equity": equity} for day, equity in zip(sessions, benchmark_values)
        ],
    }
    portfolios["cash"] = {
        "metrics": performance([parameters.initial_capital] * len(sessions), parameters.initial_capital),
        "daily": [{"date": day.date().isoformat(), "equity": parameters.initial_capital} for day in sessions],
    }
    strategy_return = portfolios["momentum_weekly"]["metrics"]["total_return"]
    for portfolio in portfolios.values():
        portfolio["metrics"]["strategy_excess_return"] = strategy_return - portfolio["metrics"]["total_return"]
    return {
        "parameters": parameters.model_dump(mode="json"),
        "actual_start": first_day.date().isoformat(),
        "actual_end": sessions[-1].date().isoformat(),
        "universe": list(STOCK_NAMES),
        "missing_volume_days": unavailable_volume,
        "warnings": [
            "固定的当前五股样本存在事后选池和幸存者偏差，结果不能代表全市场。",
            "采用后复权价格及可分割份额近似再投资；不逐笔处理分红、整手、最低佣金与公司行动。",
            "成交仅检查当日成交量；尚未模拟涨跌停、ST、盘口容量和真实开盘可成交性。",
            "成交量缺失按不可成交处理，价格仍用于估值；缺失数量见 missing_volume_days。",
            "费率为全区间固定研究假设，不代表各历史日期的实际税费；滑点买卖双向计入。",
            "沪深300为未扣费价格指数，不含分红；现金按零利息；夏普采用零无风险利率。",
            "日历来自本地沪深300行情，缺失交易日历或行情应先补齐；期末按收盘估值，不强制清仓。",
        ],
        "decisions": [{"date": day.date().isoformat(), **decision} for day, decision in decisions.items()],
        "portfolios": portfolios,
    }
