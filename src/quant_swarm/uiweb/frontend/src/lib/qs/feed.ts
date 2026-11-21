/** Polling feed with the same subscribe API surface as lib/binance/ws.ts.
 *  Klines poll /api/market/{symbol}; mini tickers poll /api/snapshot. */
"use client";

import { fetchKlines, fetchSnapshot } from "./api";
import type { Candle, InfoCardRow } from "./types";

interface KlineSub {
  symbol: string;
  onCandle: (c: Candle) => void;
}
interface TickerSub {
  symbols: string[];
  onTick: (t: { symbol: string; close: number; open: number; pct: number }) => void;
}

function lastCloseBy(cards: InfoCardRow[]) {
  const out: Record<string, { close: number; prev: number }> = {};
  for (const c of cards) {
    if (String(c.kind).split(".").pop() !== "market") continue;
    const closes = (c.payload?.closes as number[] | undefined) ?? [];
    if (!closes.length) continue;
    for (const s of c.symbols ?? []) {
      if (!(s in out))
        out[s] = { close: closes[closes.length - 1], prev: closes[closes.length - 2] ?? closes[closes.length - 1] };
    }
  }
  return out;
}

class QsFeed {
  private klineSubs = new Map<number, KlineSub>();
  private tickerSubs = new Map<number, TickerSub>();
  private seq = 0;
  private klineTimer: ReturnType<typeof setInterval> | null = null;
  private tickerTimer: ReturnType<typeof setInterval> | null = null;

  private ensureKlineLoop() {
    if (this.klineTimer) return;
    this.klineTimer = setInterval(() => {
      for (const sub of this.klineSubs.values()) {
        fetchKlines(sub.symbol)
          .then((ks) => {
            const last = ks[ks.length - 1];
            if (last) sub.onCandle(last);
          })
          .catch(() => {});
      }
    }, 15_000);
  }

  private ensureTickerLoop() {
    if (this.tickerTimer) return;
    const fire = () => {
      fetchSnapshot()
        .then((snap) => {
          const last = lastCloseBy(snap.cards ?? []);
          for (const sub of this.tickerSubs.values()) {
            for (const s of sub.symbols) {
              const t = last[s];
              if (t)
                sub.onTick({
                  symbol: s,
                  close: t.close,
                  open: t.prev,
                  pct: t.prev ? ((t.close - t.prev) / t.prev) * 100 : 0,
                });
            }
          }
        })
        .catch(() => {});
    };
    this.tickerTimer = setInterval(fire, 4_000);
    fire();
  }

  subscribeKline(sub: KlineSub): () => void {
    const id = ++this.seq;
    this.klineSubs.set(id, sub);
    this.ensureKlineLoop();
    return () => {
      this.klineSubs.delete(id);
      if (!this.klineSubs.size && this.klineTimer) {
        clearInterval(this.klineTimer);
        this.klineTimer = null;
      }
    };
  }

  subscribeMiniTickers(
    symbols: string[],
    onTick: TickerSub["onTick"],
  ): () => void {
    const id = ++this.seq;
    this.tickerSubs.set(id, { symbols, onTick });
    this.ensureTickerLoop();
    return () => {
      this.tickerSubs.delete(id);
      if (!this.tickerSubs.size && this.tickerTimer) {
        clearInterval(this.tickerTimer);
        this.tickerTimer = null;
      }
    };
  }
}

let feed: QsFeed | null = null;
/** Drop-in replacement for getBinanceWS(). */
export function getQsFeed(): QsFeed {
  feed ??= new QsFeed();
  return feed;
}
