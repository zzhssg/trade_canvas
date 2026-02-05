export type PositionToolType = "long" | "short";

export type PriceTimePoint = {
  time: number; // unix seconds
  price: number;
};

export type PositionCoordinates = {
  entry: PriceTimePoint;
  stopLoss: { price: number };
  takeProfit: { price: number };
};

export type PositionSettings = {
  accountSize?: number;
  riskAmount?: number;
  quantity?: number;
  timeSpanSeconds?: number;
  colorSettings?: {
    profitColor?: string;
    lossColor?: string;
    opacity?: number;
  };
};

export type PositionInst = {
  id: string;
  type: PositionToolType;
  coordinates: PositionCoordinates;
  settings: PositionSettings;
};

export type FibToolType = "fib_retracement";

export type FibAnchorPoint = PriceTimePoint;

export type FibSettings = {
  lineWidth?: number;
  levels?: number[];
  showLabels?: boolean;
};

export type FibInst = {
  id: string;
  type: FibToolType;
  anchors: { a: FibAnchorPoint; b: FibAnchorPoint };
  settings: FibSettings;
};

