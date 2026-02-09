import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./layout/AppShell";
import { BacktestPage } from "./pages/BacktestPage";
import { DevPage } from "./pages/DevPage";
import { LivePage } from "./pages/LivePage";
import { OraclePage } from "./pages/OraclePage";
import { ReplayPage } from "./pages/ReplayPage";
import { SettingsPage } from "./pages/SettingsPage";

const ENABLE_TRADE_ORACLE_PAGE = String(import.meta.env.VITE_ENABLE_TRADE_ORACLE_PAGE ?? "1") === "1";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/live" replace />} />
        <Route path="/live" element={<LivePage />} />
        <Route path="/oracle" element={ENABLE_TRADE_ORACLE_PAGE ? <OraclePage /> : <Navigate to="/live" replace />} />
        <Route path="/replay" element={<ReplayPage />} />
        <Route path="/backtest" element={<BacktestPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/dev" element={<DevPage />} />
      </Route>
    </Routes>
  );
}
