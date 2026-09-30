"""Regression: the lake cache must not mix up two routes that share a
function name (market.summary vs backtest.summary) when the lake files have
identical mtimes, as in a deployed snapshot."""
from gridalpha.api.deps import lake_cached


def _make(module: str, value: str, table: str):
    def summary():
        return value
    summary.__module__ = module
    return lake_cached(table)(summary)


def test_same_name_different_routes_do_not_collide():
    market = _make("gridalpha.api.routers.market", "market", "no_such_table_a")
    backtest = _make("gridalpha.api.routers.backtest", "backtest", "no_such_table_b")
    assert backtest() == "backtest"
    assert market() == "market"
    assert backtest() == "backtest"