"use client";

import { useState } from "react";
import { MessageSquareText, List } from "lucide-react";
import { Watchlist } from "@/components/watchlist/Watchlist";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "chat", label: "AI 助手", icon: MessageSquareText },
  { key: "watch", label: "自选", icon: List },
] as const;

export function RightSidebar() {
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("chat");
  return (
    <aside className="flex w-80 flex-col border-l border-tv-border bg-tv-panel">
      <div className="flex border-b border-tv-border">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 border-b-2 py-2.5 text-[11.5px] font-medium transition-colors",
              tab === key
                ? "border-tv-blue text-tv-blue"
                : "border-transparent text-tv-text-muted hover:text-tv-text",
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>
      <div className="flex min-h-0 flex-1">
        {tab === "chat" ? <ChatPanel /> : <Watchlist />}
      </div>
    </aside>
  );
}
