import { Outlet } from "react-router-dom";

import { BottomTabs } from "../parts/BottomTabs";
import { Sidebar } from "../parts/Sidebar";
import { TopBar } from "../parts/TopBar";
import { useUiStore } from "../state/uiStore";
import { useEffect } from "react";

export function AppShell() {
  const { bottomCollapsed, bottomHeight, setBottomHeight, sidebarCollapsed, sidebarWidth, setSidebarWidth } =
    useUiStore();

  useEffect(() => {
    if (bottomCollapsed) return;
    if (bottomHeight < 40) setBottomHeight(240);
  }, [bottomCollapsed, bottomHeight, setBottomHeight]);

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-[#0b0f14]">
      <TopBar />
      <div className="min-h-0 flex-1 overflow-hidden">
        <div className="flex h-full w-full overflow-hidden">
          <div style={{ width: sidebarCollapsed ? 48 : sidebarWidth }} className="shrink-0">
            <Sidebar />
          </div>
          <ResizeX onResize={setSidebarWidth} collapsed={sidebarCollapsed} />
          <div className="min-w-0 flex-1 overflow-hidden">
            <div className="h-full w-full overflow-y-auto overscroll-contain">
              <div
                className="relative w-full overflow-hidden"
                style={{
                  height: bottomCollapsed ? "100%" : `calc(100% - ${bottomHeight}px)`,
                  minHeight: bottomCollapsed ? undefined : 240
                }}
              >
                <Outlet />
                {bottomCollapsed ? null : <ResizePeek peek={bottomHeight} onResize={setBottomHeight} />}
              </div>
              <div
                className="w-full"
                style={{
                  height: bottomCollapsed ? 40 : "100%",
                  minHeight: bottomCollapsed ? 40 : "100%"
                }}
              >
                <BottomTabs />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function ResizeX({ onResize, collapsed }: { onResize: (width: number) => void; collapsed: boolean }) {
  if (collapsed) return null;
  return (
    <div
      className="h-full w-1 cursor-col-resize bg-transparent hover:bg-white/10"
      onMouseDown={(event) => {
        const startX = event.clientX;
        const sidebarEl = (event.currentTarget.previousElementSibling as HTMLElement | null)?.firstElementChild as
          | HTMLElement
          | null;
        const startWidth = sidebarEl?.offsetWidth ?? 280;

        const onMove = (e: MouseEvent) => onResize(clamp(startWidth + (e.clientX - startX), 220, 520));
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

function ResizePeek({ peek, onResize }: { peek: number; onResize: (height: number) => void }) {
  return (
    <div
      className="absolute bottom-0 left-0 h-1 w-full cursor-row-resize bg-transparent hover:bg-white/10"
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
    />
  );
}
