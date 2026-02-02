/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_BINANCE_SPOT_BASE_URL?: string;
  readonly VITE_BINANCE_FUTURES_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

