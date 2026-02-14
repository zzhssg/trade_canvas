import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell, StandalonePageShell } from "./layout/AppShell";

const ENABLE_TRADE_ORACLE_PAGE = String(import.meta.env.VITE_ENABLE_TRADE_ORACLE_PAGE ?? "1") === "1";
const BacktestPage = lazy(async () => {
  const module = await import("./pages/BacktestPage");
  return { default: module.BacktestPage };
});
const DevPage = lazy(async () => {
  const module = await import("./pages/DevPage");
  return { default: module.DevPage };
});
const LivePage = lazy(async () => {
  const module = await import("./pages/LivePage");
  return { default: module.LivePage };
});
const OraclePage = lazy(async () => {
  const module = await import("./pages/OraclePage");
  return { default: module.OraclePage };
});
const ReplayPage = lazy(async () => {
  const module = await import("./pages/ReplayPage");
  return { default: module.ReplayPage };
});
const SettingsPage = lazy(async () => {
  const module = await import("./pages/SettingsPage");
  return { default: module.SettingsPage };
});

function RouteLoadingFallback() {
  return <div className="p-4 text-xs text-white/60">Loading page...</div>;
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/live" replace />} />
        <Route
          path="/live"
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <LivePage />
            </Suspense>
          }
        />
        <Route
          path="/replay"
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <ReplayPage />
            </Suspense>
          }
        />
        <Route
          path="/backtest"
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <BacktestPage />
            </Suspense>
          }
        />
      </Route>
      <Route element={<StandalonePageShell />}>
        <Route
          path="/oracle"
          element={
            ENABLE_TRADE_ORACLE_PAGE ? (
              <Suspense fallback={<RouteLoadingFallback />}>
                <OraclePage />
              </Suspense>
            ) : (
              <Navigate to="/live" replace />
            )
          }
        />
        <Route
          path="/settings"
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <SettingsPage />
            </Suspense>
          }
        />
        <Route
          path="/dev"
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <DevPage />
            </Suspense>
          }
        />
      </Route>
    </Routes>
  );
}
