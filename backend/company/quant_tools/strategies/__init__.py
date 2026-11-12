"""策略訊號與回測封裝（自 backend.company.quant_tools.strategies 套件化）。

對外 import 路徑不變：backend.company.quant_tools.strategies 物件照舊可 import
所有私有 runner（backtest.py／strategies_advanced.py 以 from .strategies import _run_* 使用）。
"""

from __future__ import annotations

from typing import Any  # noqa: F401

from ..indicators import (  # noqa: F401
    _calmar,
    _ema,
    _max_drawdown,
    _rolling_ext,
    _rolling_std,
    _rsi,
    _sharpe,
    _sma,
    _sortino,
)
from .charts import _chart_points, _pack_backtest  # noqa: F401
from .runner import (  # noqa: F401
    _kdj_lines,
    _run_bollinger,
    _run_breakout,
    _run_donchian,
    _run_ema_cross,
    _run_kdj,
    _run_mean_reversion,
    _run_momentum,
    _run_position_series,
    _run_rsi,
    _run_triple_ma,
    _run_turtle,
)
from .volume import (  # noqa: F401
    _candle_streak,
    _run_cci,
    _run_enhanced_volume,
    _run_single_volume,
    _run_volume_price,
    _run_williams,
    _volume_heat,
)

# 子模組名稱不留在套件公開命名空間（重構前 dir() 公開集合只有 Any／annotations）
for _submodule in ("charts", "runner", "volume"):
    globals().pop(_submodule, None)
del _submodule
