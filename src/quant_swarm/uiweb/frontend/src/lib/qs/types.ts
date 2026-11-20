/** Quant$warm backend API types — replaces lib/binance/types.ts. */

export type Timeframe = "1d";

export interface Candle {
  time: number; // unix seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  isFinal?: boolean;
}

export interface MarketBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MarketPayload {
  interval?: string;
  adjust?: string;
  closes?: number[];
  bars?: MarketBar[];
  indicators?: Record<string, unknown>;
}

export interface MarketCard {
  card_id: string;
  agent: string;
  kind: string;
  symbols: string[];
  asof: string;
  source: string;
  payload: MarketPayload;
}

export interface HeartbeatRow {
  agent: string;
  ts: string;
  state?: string;
  metrics?: Record<string, unknown>;
}

export interface InfoCardRow {
  card_id: string;
  agent: string;
  kind: string;
  symbols: string[];
  asof: string;
  ttl_sec?: number;
  confidence?: number;
  source?: string;
  payload?: Record<string, unknown>;
}

export interface DecisionRow {
  ts: string;
  symbol: string;
  action: string;
  qty?: number;
  target_weight?: number;
  llm?: { model?: string };
  card_refs?: string[];
}

export interface FillRow {
  ts: string;
  order_id: string;
  status: string;
  filled_qty: number;
  avg_price: number;
  broker?: string;
}

export interface RiskRow {
  ts: string;
  level: string;
  code?: string;
  symbols?: string[];
  veto?: boolean;
  message?: string;
}

export interface ChatRow {
  session_id: string;
  role: "user" | "expert" | string;
  expert?: string | null;
  channel?: string;
  content: string;
  refs?: string[];
  ts?: string;
}

export interface PositionRow {
  symbol: string;
  qty: number;
  avg_cost: number;
}

export interface AccountRow {
  cash: number;
  equity: number;
  updated_ts?: string;
}

export interface ReportRow {
  kind: string;
  agent?: string;
  summary: string;
  ts: string;
}

export interface Snapshot {
  agents: HeartbeatRow[];
  cards: InfoCardRow[];
  decisions: DecisionRow[];
  fills: FillRow[];
  risk: RiskRow[];
  chat: ChatRow[];
  chat_session_id: string;
  account: AccountRow | null;
  positions: PositionRow[];
  reports: ReportRow[];
  watchlist: string[];
}
