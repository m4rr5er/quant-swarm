"use client";

import { useMemo } from "react";
import { Plus, X } from "lucide-react";
import { useChartStore } from "@/lib/store/chart-store";
import { useSnapshotStore } from "@/lib/qs/snapshot-store";
import { ScrollArea } from "@/components/ui/scroll-area";
import { formatPrice, formatPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/** A股约定：红涨绿跌 — display pct with tv-red/tv-green swapped vs crypto. */
export function Watchlist() {
  const extraWatch = useChartStore((s) => s.watchlist);
  const symbol = useChartStore((s) => s.symbol);
  const setSymbol = useChartStore((s) => s.setSymbol);
  const removeFromWatchlist = useChartStore((s) => s.removeFromWatchlist);
  const openSymbolDialog = useChartStore((s) => s.setSymbolDialogOpen);
  const snapWatch = useSnapshotStore((s) => s.snap?.watchlist) ?? [];
  const cards = useSnapshotStore((s) => s.snap?.cards) ?? [];

  const watchlist = useMemo(
    () => [...new Set([...snapWatch, ...extraWatch])],
    [snapWatch, extraWatch],
  );

  const rows = useMemo(() => {
    const out: Record<string, { price: number; pct: number }> = {};
    for (const c of cards) {
      if (String(c.kind).split(".").pop() !== "market") continue;
      const closes = (c.payload?.closes as number[] | undefined) ?? [];
      if (closes.length < 2) continue;
      for (const s of c.symbols ?? []) {
        if (!(s in out)) {
          const last = closes[closes.length - 1];
          const prev = closes[closes.length - 2];
          out[s] = { price: last, pct: prev ? ((last - prev) / prev) * 100 : 0 };
        }
      }
    }
    return out;
  }, [cards]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-tv-border px-3 py-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-tv-text-muted">
          自选
        </h2>
        <button
          onClick={() => openSymbolDialog(true)}
          className="rounded p-1 text-tv-text-muted hover:bg-tv-panel-hover hover:text-tv-text"
          title="添加标的"
          aria-label="添加标的"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="grid grid-cols-[1fr_auto_auto] gap-2 border-b border-tv-border px-3 py-1.5 text-[10px] uppercase tracking-wider text-tv-text-dim">
        <span>标的</span>
        <span className="text-right">现价</span>
        <span className="text-right">涨跌</span>
      </div>
      <ScrollArea className="flex-1">
        <div className="flex flex-col">
          {watchlist.map((s) => {
            const row = rows[s];
            const isActive = s === symbol;
            return (
              <div
                key={s}
                onClick={() => setSymbol(s)}
                className={cn(
                  "group grid cursor-pointer grid-cols-[1fr_auto_auto] items-center gap-2 px-3 py-1.5 text-xs transition-colors",
                  "hover:bg-tv-panel-hover",
                  isActive && "bg-tv-panel-hover",
                )}
              >
                <span className="font-medium tabular-nums text-tv-text">{s}</span>
                <span className="text-right tabular-nums text-tv-text">
                  {row ? formatPrice(row.price) : "—"}
                </span>
                <div className="flex items-center justify-end gap-1">
                  <span
                    className={cn(
                      "tabular-nums",
                      row
                        ? row.pct >= 0
                          ? "text-tv-red"
                          : "text-tv-green"
                        : "text-tv-text-muted",
                    )}
                  >
                    {row ? formatPct(row.pct) : "—"}
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      removeFromWatchlist(s);
                    }}
                    className="invisible rounded p-0.5 text-tv-text-muted hover:bg-tv-bg hover:text-tv-red group-hover:visible"
                    aria-label={`移除 ${s}`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              </div>
            );
          })}
          {watchlist.length === 0 && (
            <div className="p-4 text-center text-xs text-tv-text-muted">
              自选为空 — 在 settings.yaml 配置 watchlist
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
