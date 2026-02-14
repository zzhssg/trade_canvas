import { Outlet } from "react-router-dom";

import { BottomTabs } from "../parts/BottomTabs";
import { Sidebar } from "../parts/Sidebar";
import { TopBar } from "../parts/TopBar";
import { ToolRail } from "../parts/ToolRail";
import { useUiStore } from "../state/uiStore";
import { CenterScrollLockProvider } from "./centerScrollLock";
import { useEffect, useMemo, useState } from "react";

export function AppShell() {
  const [centerScrollLocked, setCenterScrollLocked] = useState(false);
  const {
    bottomCollapsed,
    sidebarCollapsed,
    sidebarWidth,
    setSidebarWidth,
    toolRailWidth,
    setToolRailWidth
  } = useUiStore();
  const scrollLockApi = useMemo(
    () => ({
      lock: () => setCenterScrollLocked(true),
      unlock: () => setCenterScrollLocked(false)
    }),
    []
  );

  useEffect(() => {
    if (bottomCollapsed) return;
  }, [bottomCollapsed]);

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-transparent">
      <TopBar />
      <div className="min-h-0 flex-1 overflow-hidden">
        <div className="flex h-full w-full overflow-hidden">
          <div style={{ width: toolRailWidth }} className="shrink-0">
            <ToolRail />
          </div>
          <ResizeX onResize={setToolRailWidth} collapsed={false} side="left" min={44} max={96} />
          <div className="min-w-0 flex-1 overflow-hidden">
            <div className="h-full w-full overflow-hidden">
              <CenterScrollLockProvider value={scrollLockApi}>
                <div
                  className={[
                    "tc-scrollbar-none h-full w-full overscroll-contain",
                    centerScrollLocked ? "overflow-hidden" : "overflow-y-auto"
                  ].join(" ")}
                  data-testid="middle-scroll"
                  data-center-scroll="true"
                >
                  <Outlet />
                  <BottomTabs />
                </div>
              </CenterScrollLockProvider>
            </div>
          </div>
          <ResizeX onResize={setSidebarWidth} collapsed={sidebarCollapsed} side="right" />
          <div style={{ width: sidebarCollapsed ? 48 : sidebarWidth }} className="shrink-0">
            <Sidebar side="right" />
          </div>
        </div>
      </div>
    </div>
  );
}

export function StandalonePageShell() {
  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-transparent">
      <TopBar />
      <div className="tc-scrollbar-none min-h-0 flex-1 overflow-y-auto">
        <Outlet />
      </div>
    </div>
  );
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function ResizeX({
  onResize,
  collapsed,
  side,
  min = 220,
  max = 520
}: {
  onResize: (width: number) => void;
  collapsed: boolean;
  side: "left" | "right";
  min?: number;
  max?: number;
}) {
  if (collapsed) return null;
  return (
    <div
      className="h-full w-1 cursor-col-resize bg-transparent hover:bg-white/10"
      onMouseDown={(event) => {
        const startX = event.clientX;
        const target =
          side === "left"
            ? ((event.currentTarget.previousElementSibling as HTMLElement | null)?.firstElementChild as HTMLElement | null)
            : ((event.currentTarget.nextElementSibling as HTMLElement | null)?.firstElementChild as HTMLElement | null);
        const startWidth = target?.offsetWidth ?? 280;

        const onMove = (e: MouseEvent) => {
          const dx = e.clientX - startX;
          const next = side === "left" ? startWidth + dx : startWidth - dx;
          onResize(clamp(next, min, max));
        };
        const onUp = () => {
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
        };

        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
      }}
    />
  );
}

// ResizeY removed: BottomTabs lives inside the middle scroll container.
