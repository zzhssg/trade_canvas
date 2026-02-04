import { useEffect } from "react";

import { ChartPanel } from "../parts/ChartPanel";
import { useUiStore } from "../state/uiStore";

export function BacktestPage() {
  const { bottomCollapsed, toggleBottomCollapsed, setActiveBottomTab } = useUiStore();

  useEffect(() => {
    setActiveBottomTab("Backtest");
    if (bottomCollapsed) toggleBottomCollapsed();
  }, [bottomCollapsed, setActiveBottomTab, toggleBottomCollapsed]);

  return <ChartPanel mode="live" />;
}
