import { Outlet } from "react-router-dom";

import { BottomTabs } from "../parts/BottomTabs";
import { Sidebar } from "../parts/Sidebar";
import { TopBar } from "../parts/TopBar";
import { ToolRail } from "../parts/ToolRail";
import { useUiStore } from "../state/uiStore";
import { useEffect } from "react";

export function AppShell() {
  const {
    bottomCollapsed,
    bottomHeight,
    setBottomHeight,
    sidebarCollapsed,
    sidebarWidth,
    setSidebarWidth,
    toolRailWidth,
    setToolRailWidth
  } = useUiStore();

  useEffect(() => {
    if (bottomCollapsed) return;
    if (bottomHeight < 40) setBottomHeight(240);
  }, [bottomCollapsed, bottomHeight, setBottomHeight]);

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-[#0b0f14]">
      <TopBar />
      <div className="min-h-0 flex-1 overflow-hidden">
        <div className="flex h-full w-full overflow-hidden">
          <div style={{ width: toolRailWidth }} className="shrink-0">
            <ToolRail />
          </div>
          <ResizeX onResize={setToolRailWidth} collapsed={false} side="left" min={44} max={96} />
          <div className="min-w-0 flex-1 overflow-hidden">
            <div className="flex h-full min-h-0 w-full flex-col overflow-hidden">
              <div className="min-h-0 flex-1 overflow-hidden">
                <Outlet />
              </div>
              <ResizeY peek={bottomHeight} onResize={setBottomHeight} collapsed={bottomCollapsed} />
              <div className="shrink-0" style={{ height: bottomCollapsed ? 40 : bottomHeight }}>
                <BottomTabs />
              </div>
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

function ResizeY({ peek, onResize, collapsed }: { peek: number; onResize: (height: number) => void; collapsed: boolean }) {
  if (collapsed) return null;
  return (
    <div
      className="h-1 w-full shrink-0 cursor-row-resize bg-transparent hover:bg-white/10"
      title="Scroll or drag to resize"
      onMouseDown={(event) => {
        const startY = event.clientY;
        const startPeek = peek;

        // Move up => larger bottom peek. Move down => smaller bottom peek.
        const onMove = (e: MouseEvent) => onResize(clamp(startPeek - (e.clientY - startY), 40, 640));
        const onUp = () => {
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
        };

        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
      }}
      onWheel={(event) => {
        event.preventDefault();
        const dy = event.deltaY;
        if (!Number.isFinite(dy) || dy === 0) return;
        const step = Math.max(8, Math.min(80, Math.abs(dy) * 0.8));
        const next = dy < 0 ? peek + step : peek - step;
        onResize(clamp(next, 40, 640));
      }}
    />
  );
}
