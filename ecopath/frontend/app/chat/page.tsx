"use client";

import { Suspense } from "react";
import { ChatPageInner } from "@/components/chat/ChatPage";

export default function ChatPage() {
  return (
    <Suspense fallback={
      <div style={{ paddingTop: 48, height: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-primary)" }}>
        <div style={{ width: 16, height: 16, border: "1px solid var(--accent-primary, #34d399)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    }>
      <ChatPageInner />
    </Suspense>
  );
}
