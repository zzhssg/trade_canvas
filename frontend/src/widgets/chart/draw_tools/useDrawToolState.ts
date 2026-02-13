import { useCallback, useEffect, useRef, useState } from "react";

import type { ChartToolKey } from "../../../state/uiStore";

import type { FibInst, PositionInst, PriceTimePoint } from "./types";

export type DrawMeasurePoint = PriceTimePoint & { x: number; y: number };

export type DrawMeasureState = {
  start: DrawMeasurePoint | null;
  current: DrawMeasurePoint | null;
  locked: boolean;
};

const EMPTY_MEASURE_STATE: DrawMeasureState = {
  start: null,
  current: null,
  locked: false
};

type UseDrawToolStateArgs = {
  enableDrawTools: boolean;
  activeChartTool: ChartToolKey;
  setActiveChartTool: (tool: ChartToolKey) => void;
  seriesId: string;
};

export function useDrawToolState({ enableDrawTools, activeChartTool, setActiveChartTool, seriesId }: UseDrawToolStateArgs) {
  const [positionTools, setPositionTools] = useState<PositionInst[]>([]);
  const [fibTools, setFibTools] = useState<FibInst[]>([]);
  const [activeToolId, setActiveToolId] = useState<string | null>(null);
  const [fibAnchorA, setFibAnchorA] = useState<PriceTimePoint | null>(null);
  const [measureState, setMeasureState] = useState<DrawMeasureState>(EMPTY_MEASURE_STATE);

  const activeChartToolRef = useRef(activeChartTool);
  const fibAnchorARef = useRef(fibAnchorA);
  const measureStateRef = useRef(measureState);
  const activeToolIdRef = useRef(activeToolId);
  const interactionLockRef = useRef<{ dragging: boolean }>({ dragging: false });
  const suppressDeselectUntilRef = useRef<number>(0);

  useEffect(() => {
    activeChartToolRef.current = activeChartTool;
  }, [activeChartTool]);

  useEffect(() => {
    fibAnchorARef.current = fibAnchorA;
  }, [fibAnchorA]);

  useEffect(() => {
    measureStateRef.current = measureState;
  }, [measureState]);

  useEffect(() => {
    activeToolIdRef.current = activeToolId;
  }, [activeToolId]);

  const genId = useCallback(() => Math.random().toString(36).substring(2, 9), []);

  const clearDrawTools = useCallback(() => {
    setPositionTools([]);
    setFibTools([]);
    setActiveToolId(null);
    setFibAnchorA(null);
    setMeasureState(EMPTY_MEASURE_STATE);
    suppressDeselectUntilRef.current = 0;
  }, []);

  useEffect(() => {
    if (!enableDrawTools) return;
    clearDrawTools();
    setActiveChartTool("cursor");
  }, [clearDrawTools, enableDrawTools, seriesId, setActiveChartTool]);

  useEffect(() => {
    if (enableDrawTools) return;
    if (activeChartTool !== "cursor") setActiveChartTool("cursor");
  }, [activeChartTool, enableDrawTools, setActiveChartTool]);

  const updatePositionTool = useCallback((id: string, updates: Partial<PositionInst>) => {
    setPositionTools((list) =>
      list.map((tool) => {
        if (tool.id !== id) return tool;
        return {
          ...tool,
          ...updates,
          coordinates: { ...tool.coordinates, ...(updates.coordinates ?? {}) },
          settings: { ...tool.settings, ...(updates.settings ?? {}) }
        };
      })
    );
  }, []);

  const removePositionTool = useCallback((id: string) => {
    setPositionTools((list) => list.filter((tool) => tool.id !== id));
    setActiveToolId((current) => (current === id ? null : current));
  }, []);

  const updateFibTool = useCallback((id: string, updates: Partial<FibInst>) => {
    setFibTools((list) =>
      list.map((tool) => {
        if (tool.id !== id) return tool;
        return {
          ...tool,
          ...updates,
          anchors: { ...tool.anchors, ...(updates.anchors ?? {}) },
          settings: { ...tool.settings, ...(updates.settings ?? {}) }
        };
      })
    );
  }, []);

  const removeFibTool = useCallback((id: string) => {
    setFibTools((list) => list.filter((tool) => tool.id !== id));
    setActiveToolId((current) => (current === id ? null : current));
  }, []);

  const selectTool = useCallback((id: string | null) => {
    if (id) suppressDeselectUntilRef.current = Date.now() + 120;
    setActiveToolId(id);
  }, []);

  return {
    positionTools,
    setPositionTools,
    fibTools,
    setFibTools,
    activeToolId,
    setActiveToolId,
    fibAnchorA,
    setFibAnchorA,
    measureState,
    setMeasureState,
    activeChartToolRef,
    fibAnchorARef,
    measureStateRef,
    activeToolIdRef,
    interactionLockRef,
    suppressDeselectUntilRef,
    genId,
    updatePositionTool,
    removePositionTool,
    updateFibTool,
    removeFibTool,
    selectTool
  };
}
