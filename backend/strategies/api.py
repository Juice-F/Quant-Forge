"""策略展示与参数预览的 FastAPI 接口。"""

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from strategies.low_volatility import strategy as low_volatility
from strategies.mean_reversion import strategy as mean_reversion
from strategies.momentum import strategy as momentum
from strategies.momentum.backtest import Parameters as MomentumBacktestParameters
from strategies.momentum.backtest import run as run_momentum_backtest

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


def strategy_module(strategy_id: str):
    match strategy_id:
        case "momentum":
            return momentum
        case "mean_reversion":
            return mean_reversion
        case "low_volatility":
            return low_volatility
        case _:
            raise HTTPException(status_code=404, detail="策略不存在。")


@router.get("")
def list_strategies() -> list[dict]:
    return [momentum.run(preview=True), mean_reversion.run(preview=True), low_volatility.run(preview=True)]


@router.get("/{strategy_id}")
def strategy_detail(strategy_id: str) -> dict:
    return strategy_module(strategy_id).run(preview=True)


@router.post("/{strategy_id}/preview")
def preview_strategy(strategy_id: str, parameters: dict) -> dict:
    strategy = strategy_module(strategy_id)
    try:
        return strategy.run(parameters, preview=True)
    except ValidationError as exc:
        errors = [
            {"loc": ["body", *error["loc"]], "msg": error["msg"], "type": error["type"]} for error in exc.errors()
        ]
        raise HTTPException(status_code=422, detail=errors) from exc


@router.post("/momentum/backtest")
def momentum_backtest(parameters: MomentumBacktestParameters) -> dict:
    """执行动量策略自己的周调仓回测。"""
    try:
        return run_momentum_backtest(parameters.model_dump())
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
