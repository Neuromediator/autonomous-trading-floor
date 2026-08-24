// Client for the trading floor HTTP API. All paths are relative; in dev the Vite
// proxy forwards /api to the FastAPI backend, so the browser sees one origin.

export interface TraderInfo {
  name: string;
  lastname: string;
  model_name: string;
}

export interface Holding {
  symbol: string;
  quantity: number;
  price: number;
  avg_cost: number;
  market_value: number;
  unrealized_pnl: number;
}

/** What the trade did to the position, not just its sign: a sale can reduce a
 *  long or open a short, and a purchase can open a long or cover a short. */
export type TradeAction = "BUY" | "SELL" | "SHORT" | "COVER";

export interface Transaction {
  symbol: string;
  quantity: number;
  price: number;
  timestamp: string;
  rationale: string;
  action: TradeAction;
}

export interface TimePoint {
  datetime: string;
  value: number;
}

// Mirrors the full backend payload; the dashboard renders a subset of these fields.
export interface RoundCost {
  day: string;
  cost: number;
  input_tokens: number;
  output_tokens: number;
  calls: number;
}

export interface Cost {
  total: number;
  input_tokens: number;
  output_tokens: number;
  calls: number;
  /** Calls whose model had no published price; their cost is missing from the totals. */
  unpriced_calls: number;
  per_round: RoundCost[];
  last_round: number;
}

export interface TraderDetail extends TraderInfo {
  balance: number;
  /** The trader's fixed mandate, set in code and not rewritable by the agent. */
  persona: string;
  strategy: string;
  /** How many times the agent has rewritten its own strategy. */
  strategy_revisions: number;
  portfolio_value: number;
  pnl: number;
  holdings: Holding[];
  transactions: Transaction[];
  /** Short market value as a share of the portfolio, and the hard limit on it. */
  short_exposure: number;
  max_short_exposure: number;
  cost: Cost;
  time_series: TimePoint[];
}

export interface LogRow {
  datetime: string;
  type: string;
  message: string;
  color: string;
}

export interface MarketInfo {
  source: "massive" | "offline";
  /** Which price the data plan serves: "last trade", "previous close", …
   *  Absent when the backend predates the field. */
  tier?: string;
  is_market_open: boolean;
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} failed: ${r.status}`);
  return r.json() as Promise<T>;
}

export function getTraders(): Promise<TraderInfo[]> {
  return get("/api/traders");
}

export function getTrader(name: string): Promise<TraderDetail> {
  return get(`/api/traders/${encodeURIComponent(name)}`);
}

// Deep enough to cover a whole trading run (a busy one produces several
// hundred rows); the payload is small and polled at a relaxed interval.
export function getTraderLogs(name: string, lastN = 300): Promise<LogRow[]> {
  return get(`/api/traders/${encodeURIComponent(name)}/logs?last_n=${lastN}`);
}

export function getMarket(): Promise<MarketInfo> {
  return get("/api/market");
}
