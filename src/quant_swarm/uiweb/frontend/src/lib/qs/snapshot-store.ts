/** Global snapshot store — polls /api/snapshot and exposes sendChat. */
"use client";

import { create } from "zustand";
import { fetchSnapshot, postChat } from "./api";
import type { Snapshot } from "./types";

interface SnapState {
  snap: Snapshot | null;
  pendingReply: boolean;
  expertBase: number;
  sendChat: (text: string) => Promise<void>;
}

export const useSnapshotStore = create<SnapState>((set, get) => ({
  snap: null,
  pendingReply: false,
  expertBase: 0,
  sendChat: async (text) => {
    const t = text.trim();
    if (!t) return;
    set({
      expertBase: (get().snap?.chat ?? []).filter((m) => m.role === "expert").length,
      pendingReply: true,
    });
    await postChat(t);
  },
}));

let started = false;
export function startSnapshotPolling() {
  if (started) return;
  started = true;
  const tick = () =>
    fetchSnapshot()
      .then((snap) => {
        const st = useSnapshotStore.getState();
        const experts = (snap.chat ?? []).filter((m) => m.role === "expert").length;
        useSnapshotStore.setState({
          snap,
          pendingReply: st.pendingReply && experts <= st.expertBase,
        });
      })
      .catch(() => {});
  tick();
  setInterval(tick, 2500);
}
