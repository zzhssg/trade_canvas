import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./layout/AppShell";
import { BacktestPage } from "./pages/BacktestPage";
import { DevPage } from "./pages/DevPage";
import { LivePage } from "./pages/LivePage";
import { ReplayPage } from "./pages/ReplayPage";
import { SettingsPage } from "./pages/SettingsPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/live" replace />} />
        <Route path="/live" element={<LivePage />} />
        <Route path="/replay" element={<ReplayPage />} />
        <Route path="/backtest" element={<BacktestPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/dev" element={<DevPage />} />
      </Route>
    </Routes>
  );
}
