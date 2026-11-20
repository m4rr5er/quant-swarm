"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { SendHorizonal } from "lucide-react";
import { useSnapshotStore } from "@/lib/qs/snapshot-store";
import type { ChatRow } from "@/lib/qs/types";
import { cn } from "@/lib/utils";

marked.setOptions({ gfm: true, breaks: true });
const md = (src: string) =>
  DOMPurify.sanitize(marked.parse(src) as string, {
    ADD_ATTR: ["target"],
  });

const EXPERT_COLOR: Record<string, string> = {
  investor: "#ffb74d",
  quant: "#2dd4bf",
  system: "#787b86",
};
const EXPERT_LETTER: Record<string, string> = {
  investor: "投",
  quant: "量",
  system: "AI",
};

function Bubble({ m }: { m: ChatRow }) {
  const user = m.role === "user";
  const html = useMemo(() => md(m.content || ""), [m.content]);
  const who = user ? "我" : (m.expert ?? "system");
  return (
    <div className={cn("flex gap-2", user && "flex-row-reverse")}>
      <div
        className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[10px] font-semibold text-white"
        style={{ background: user ? "#2962ff" : EXPERT_COLOR[m.expert ?? "system"] }}
      >
        {user ? "我" : (EXPERT_LETTER[m.expert ?? "system"] ?? "AI")}
      </div>
      <div className={cn("min-w-0 max-w-[88%]", user && "text-right")}>
        <div className="mb-0.5 flex items-baseline gap-1.5 text-[10px] text-tv-text-dim">
          <span
            className="font-semibold"
            style={{ color: user ? "#2962ff" : EXPERT_COLOR[m.expert ?? "system"] }}
          >
            {who}
          </span>
          {m.ts && <span>{new Date(m.ts).toLocaleTimeString("zh-CN", { hour12: false })}</span>}
        </div>
        <div
          className={cn(
            "md-body rounded-lg px-2.5 py-1.5 text-left text-[12.5px] leading-relaxed",
            user ? "bg-tv-blue text-white" : "bg-tv-panel-hover text-tv-text",
          )}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </div>
    </div>
  );
}

export function ChatPanel() {
  const chat = useSnapshotStore((s) => s.snap?.chat) ?? [];
  const pending = useSnapshotStore((s) => s.pendingReply);
  const sendChat = useSnapshotStore((s) => s.sendChat);
  const [text, setText] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const atBottom = useRef(true);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && atBottom.current) el.scrollTop = el.scrollHeight;
  }, [chat.length, pending]);

  const submit = () => {
    const t = text.trim();
    if (!t) return;
    setText("");
    if (taRef.current) taRef.current.style.height = "auto";
    atBottom.current = true;
    void sendChat(t);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        className="min-h-0 flex-1 space-y-3 overflow-y-auto px-2.5 py-3"
      >
        {chat.length === 0 && (
          <div className="py-8 text-center text-xs text-tv-text-dim">
            问专家任何问题 — 例如「茅台现在能建仓吗」
          </div>
        )}
        {chat.map((m, i) => (
          <Bubble key={i} m={m} />
        ))}
        {pending && (
          <div className="flex gap-2">
            <div className="mt-0.5 flex h-6 w-6 items-center justify-center rounded-md bg-tv-panel-hover text-[10px] font-semibold text-tv-text-muted">
              AI
            </div>
            <div className="flex items-center gap-1 rounded-lg bg-tv-panel-hover px-3 py-2">
              <span className="chat-dot" />
              <span className="chat-dot" style={{ animationDelay: "0.15s" }} />
              <span className="chat-dot" style={{ animationDelay: "0.3s" }} />
            </div>
          </div>
        )}
      </div>
      <div className="border-t border-tv-border p-2">
        <div className="flex items-end gap-1.5">
          <textarea
            ref={taRef}
            value={text}
            rows={1}
            placeholder="给决策 AI 下达任务…"
            onChange={(e) => {
              setText(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
            }}
            onKeyDown={(e) => {
              if (e.key !== "Enter" || e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return;
              if (e.nativeEvent.isComposing || e.keyCode === 229) return;
              e.preventDefault();
              if (!e.repeat) submit();
            }}
            className="max-h-28 min-h-8 flex-1 resize-none rounded-md border border-tv-border bg-tv-bg px-2.5 py-1.5 text-xs text-tv-text outline-none placeholder:text-tv-text-dim focus:border-tv-blue"
          />
          <button
            onClick={submit}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-tv-blue text-white transition-colors hover:bg-tv-blue/85"
            aria-label="发送"
          >
            <SendHorizonal className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
