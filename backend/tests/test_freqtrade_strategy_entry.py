from __future__ import annotations

import ast
from pathlib import Path


def test_trade_canvas_strategy_imports_new_freqtrade_adapter_path() -> None:
    strategy_file = Path(__file__).resolve().parents[2] / "Strategy" / "TradeCanvasFactorLedgerStrategy.py"
    tree = ast.parse(strategy_file.read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and isinstance(node.module, str)
        and node.module
    }
    assert "backend.app.freqtrade.adapter_v1" in imports
    assert "backend.app.freqtrade_adapter_v1" not in imports
