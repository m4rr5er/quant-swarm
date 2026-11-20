/** Quant$warm REST calls — replaces lib/binance/rest.ts. */
import type { Candle, MarketCard, Snapshot } from "./types";

/** "2026-11-20" -> unix seconds (UTC midnight) for lightweight-charts. */
export function dateToTime(date: string): number {
  const [y, m, d] = date.split("-").map(Number);
  return Date.UTC(y, m - 1, d) / 1000;
}

export async function fetchMarketCard(symbol: string): Promise<MarketCard | null> {
  const res = await fetch(`/api/market/${encodeURIComponent(symbol)}`, {
    cache: "no-store",
  });
  if (!res.ok) return null;
  const d = (await res.json()) as MarketCard & { error?: string };
  return d.error ? null : d;
}

/** Signature-compatible klines fetch: daily bars -> Candle[]. */
export async function fetchKlines(symbol: string): Promise<Candle[]> {
  const card = await fetchMarketCard(symbol);
  const bars = card?.payload?.bars ?? [];
  return bars.map((b) => ({
    time: dateToTime(b.date),
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
    volume: b.volume,
    isFinal: true,
  }));
}

export async function fetchSnapshot(): Promise<Snapshot> {
  const res = await fetch("/api/snapshot", { cache: "no-store" });
  if (!res.ok) throw new Error(`snapshot ${res.status}`);
  return (await res.json()) as Snapshot;
}

export async function postChat(text: string): Promise<void> {
  await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

export async function fetchFiles(): Promise<Record<string, string>> {
  const res = await fetch("/api/files", { cache: "no-store" });
  if (!res.ok) return {};
  return (await res.json()) as Record<string, string>;
}
