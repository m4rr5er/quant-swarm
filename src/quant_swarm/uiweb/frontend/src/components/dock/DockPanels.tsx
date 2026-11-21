"use client";

import { useEffect, useState } from "react";
import { fetchFiles } from "@/lib/qs/api";
import { useSnapshotStore } from "@/lib/qs/snapshot-store";
import { cn } from "@/lib/utils";

const fmtT = (ts?: string) =>
  ts ? new Date(ts).toLocaleTimeString("zh-CN", { hour12: false }) : "-";
const num = (n?: number | null, d = 2) =>
  n == null ? "-" : n.toLocaleString("zh-CN", { maximumFractionDigits: d });

function T({
  heads,
  rows,
}: {
  heads: string[];
  rows: React.ReactNode[][];
}) {
  return (
    <table className="w-full text-[11.5px]">
      <thead>
        <tr className="text-left text-tv-text-dim">
          {heads.map((h) => (
            <th key={h} className="border-b border-tv-border px-3 py-1.5 font-medium">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 && (
          <tr>
            <td colSpan={heads.length} className="px-3 py-4 text-center text-tv-text-dim">
              暂无数据
            </td>
          </tr>
        )}
        {rows.map((r, i) => (
          <tr key={i} className="border-b border-tv-border/40 hover:bg-tv-panel-hover/40">
            {r.map((c, j) => (
              <td key={j} className="px-3 py-1.5 tabular-nums">
                {c}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Pill({ v }: { v: string }) {
  const act = v.split(".").pop() ?? v;
  const cls =
    act === "BUY" || act === "online"
      ? "bg-tv-green/15 text-tv-green"
      : act === "SELL" || act === "CRITICAL" || act === "down" || act === "veto"
        ? "bg-tv-red/15 text-tv-red"
        : act === "WARN" || act === "stale"
          ? "bg-tv-yellow/15 text-tv-yellow"
          : "bg-tv-panel-hover text-tv-text-muted";
  return <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-medium", cls)}>{act}</span>;
}

export function PositionsPanel() {
  const snap = useSnapshotStore((s) => s.snap);
  const acc = snap?.account;
  const pos = (snap?.positions ?? []).filter((p) => p.qty);
  return (
    <div>
      <div className="flex gap-4 border-b border-tv-border px-3 py-1.5 text-[11px] text-tv-text-muted">
        <span>现金 <b className="text-tv-text">{num(acc?.cash, 0)}</b></span>
        <span>总资产 <b className="text-tv-text">{num(acc?.equity, 0)}</b></span>
        <span>更新 {fmtT(acc?.updated_ts)}</span>
      </div>
      <T
        heads={["标的", "数量", "成本"]}
        rows={pos.map((p) => [p.symbol, num(p.qty, 0), num(p.avg_cost)])}
      />
    </div>
  );
}

export function FillsPanel() {
  const fills = useSnapshotStore((s) => s.snap?.fills) ?? [];
  return (
    <T
      heads={["时间", "订单", "状态", "数量", "价格", "通道"]}
      rows={fills.map((f) => [
        <span className="text-tv-text-muted">{fmtT(f.ts)}</span>,
        <span className="text-tv-text-muted">{String(f.order_id ?? "").slice(-8)}</span>,
        <Pill v={String(f.status ?? "").split(".").pop() ?? ""} />,
        num(f.filled_qty, 0),
        num(f.avg_price),
        <span className="text-tv-text-muted">{f.broker}</span>,
      ])}
    />
  );
}

export function DecisionsPanel() {
  const decs = useSnapshotStore((s) => s.snap?.decisions) ?? [];
  return (
    <T
      heads={["时间", "标的", "动作", "数量", "目标仓位", "模型"]}
      rows={decs.map((d) => [
        <span className="text-tv-text-muted">{fmtT(d.ts)}</span>,
        d.symbol,
        <Pill v={String(d.action)} />,
        num(d.qty, 0),
        d.target_weight != null ? `${(d.target_weight * 100).toFixed(0)}%` : "-",
        <span className="text-tv-text-muted">{d.llm?.model ?? "policy"}</span>,
      ])}
    />
  );
}

export function AgentsPanel() {
  const agents = useSnapshotStore((s) => s.snap?.agents) ?? [];
  const now = Date.now() / 1000;
  return (
    <T
      heads={["组件", "状态", "心跳", "指标"]}
      rows={[...agents]
        .sort((a, b) => a.agent.localeCompare(b.agent))
        .map((a) => {
          const age = Math.max(0, now - new Date(a.ts).getTime() / 1000);
          return [
            a.agent,
            <Pill v={age < 20 ? "online" : age < 120 ? "stale" : "down"} />,
            <span className="text-tv-text-muted">{fmtT(a.ts)}</span>,
            <span className="text-tv-text-dim">{JSON.stringify(a.metrics ?? {})}</span>,
          ];
        })}
    />
  );
}

export function RiskPanel() {
  const risk = useSnapshotStore((s) => s.snap?.risk) ?? [];
  return (
    <T
      heads={["时间", "等级", "代码", "标的", "veto", "内容"]}
      rows={risk.map((e) => [
        <span className="text-tv-text-muted">{fmtT(e.ts)}</span>,
        <Pill v={String(e.level ?? "")} />,
        e.code ?? "-",
        (e.symbols ?? []).join(","),
        e.veto ? <Pill v="veto" /> : "",
        <span className="text-tv-text-muted">{e.message}</span>,
      ])}
    />
  );
}

export function LearningPanel() {
  const reports = useSnapshotStore((s) => s.snap?.reports) ?? [];
  const [files, setFiles] = useState<Record<string, string>>({});
  const [sel, setSel] = useState<string | null>(null);
  useEffect(() => {
    fetchFiles().then(setFiles).catch(() => {});
  }, []);
  const names = Object.keys(files).sort();
  return (
    <div className="flex h-full">
      <div className="w-44 shrink-0 overflow-y-auto border-r border-tv-border py-1">
        {names.map((n) => (
          <button
            key={n}
            onClick={() => setSel(n)}
            className={cn(
              "block w-full truncate px-3 py-1 text-left font-mono text-[10.5px] hover:bg-tv-panel-hover",
              sel === n ? "text-tv-blue" : "text-tv-text-muted",
            )}
          >
            {n}
          </button>
        ))}
      </div>
      <div className="min-w-0 flex-1 overflow-auto p-2">
        {sel ? (
          <pre className="whitespace-pre-wrap font-mono text-[10.5px] leading-relaxed text-tv-text-muted">
            {files[sel] || "(空)"}
          </pre>
        ) : (
          <div className="space-y-1.5">
            {reports.length === 0 && (
              <div className="py-4 text-center text-[11px] text-tv-text-dim">
                暂无学习报告 — qs trigger learn 跑一轮；或从左侧查看记忆/技能文件
              </div>
            )}
            {reports.slice(0, 10).map((r, i) => (
              <div key={i} className="rounded border border-tv-border/60 px-2.5 py-1.5">
                <div className="mb-0.5 flex gap-2 text-[10px] text-tv-text-dim">
                  <Pill v={r.kind} />
                  <span>{fmtT(r.ts)}</span>
                  <span>{r.agent ?? "system"}</span>
                </div>
                <div className="text-[11px] text-tv-text-muted">{r.summary}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
