"use client";

import { useEffect, useRef, useState } from "react";

export default function HomePage() {
  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: "0 auto" }}>
      <Header />
      <StatusBar />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginTop: 20 }}>
        <AccountsPanel />
        <GroupsPanel />
      </div>
      <MappingsPanel />
      <LogPanel />
    </div>
  );
}

function Header() {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700 }}>TG → Discord Identity Bridge</h1>
      <div style={{ display: "flex", gap: 10 }}>
        <StatusBadge label="Telegram" online={true} />
        <StatusBadge label="Discord Selfbots" online={true} />
        <StatusBadge label="Forwarder" online={true} />
      </div>
    </div>
  );
}

function StatusBadge({ label, online }: { label: string; online: boolean }) {
  return (
    <span
      style={{
        padding: "4px 12px",
        borderRadius: 12,
        fontSize: 12,
        background: online ? "#1a3a1a" : "#3a1a1a",
        color: online ? "#5f5" : "#f55",
        border: `1px solid ${online ? "#2a5a2a" : "#5a2a2a"}`,
      }}
    >
      {online ? "●" : "○"} {label}
    </span>
  );
}

function StatusBar() {
  return (
    <div style={{ marginTop: 16, padding: "12px 16px", borderRadius: 8, background: "#1a1a1a", border: "1px solid #333" }}>
      <div style={{ display: "flex", gap: 40 }}>
        <Stat label="TG Groups Monitored" value="3" />
        <Stat label="Discord Accounts" value="25" />
        <Stat label="Mapped Identities" value="18" />
        <Stat label="Msgs Forwarded" value="1,247" />
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ fontSize: 12, color: "#888" }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

function AccountsPanel() {
  const accounts = [
    { id: "acc01", name: "selfbot-alice", avatar: "", tgUser: "@alice_tg", role: "VIP", status: "online" },
    { id: "acc02", name: "selfbot-bob", avatar: "", tgUser: "@bob_tg", role: "TG Member", status: "synced" },
    { id: "acc03", name: "selfbot-carol", avatar: "", tgUser: "@carol_tg", role: "TG Member", status: "pending" },
  ];

  return (
    <Panel title="Discord Selfbot Accounts" count={accounts.length}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ color: "#888", textAlign: "left" }}>
            <th style={{ padding: 6 }}>Selfbot</th>
            <th style={{ padding: 6 }}>TG User</th>
            <th style={{ padding: 6 }}>Role</th>
            <th style={{ padding: 6 }}>Status</th>
          </tr>
        </thead>
        <tbody>
          {accounts.map((a) => (
            <tr key={a.id} style={{ borderTop: "1px solid #222" }}>
              <td style={{ padding: 6, fontWeight: 600 }}>{a.name}</td>
              <td style={{ padding: 6, color: "#8af" }}>{a.tgUser}</td>
              <td style={{ padding: 6 }}>
                <span style={{ padding: "2px 8px", borderRadius: 4, background: "#222", fontSize: 11 }}>{a.role}</span>
              </td>
              <td style={{ padding: 6 }}>
                <span
                  style={{
                    padding: "2px 8px",
                    borderRadius: 4,
                    fontSize: 11,
                    background: a.status === "synced" ? "#1a3a1a" : a.status === "online" ? "#1a2a3a" : "#3a3a1a",
                    color: a.status === "synced" ? "#5f5" : a.status === "online" ? "#5af" : "#aa5",
                  }}
                >
                  {a.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function GroupsPanel() {
  const groups = [
    { id: "-100123456", label: "Crypto Signals", members: 45, discord: "#signals", forwarding: true },
    { id: "-100789012", label: "Dev Chat", members: 12, discord: "#dev-chat", forwarding: true },
    { id: "-100345678", label: "VIP Lounge", members: 8, discord: "#vip", forwarding: false },
  ];

  return (
    <Panel title="Telegram Groups" count={groups.length}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ color: "#888", textAlign: "left" }}>
            <th style={{ padding: 6 }}>Group</th>
            <th style={{ padding: 6 }}>Members</th>
            <th style={{ padding: 6 }}>Discord</th>
            <th style={{ padding: 6 }}>Fwding</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => (
            <tr key={g.id} style={{ borderTop: "1px solid #222" }}>
              <td style={{ padding: 6, fontWeight: 600 }}>{g.label}</td>
              <td style={{ padding: 6 }}>{g.members}</td>
              <td style={{ padding: 6, color: "#8af" }}>{g.discord}</td>
              <td style={{ padding: 6 }}>
                <span
                  style={{
                    padding: "2px 8px",
                    borderRadius: 4,
                    fontSize: 11,
                    background: g.forwarding ? "#1a3a1a" : "#3a1a1a",
                    color: g.forwarding ? "#5f5" : "#f55",
                  }}
                >
                  {g.forwarding ? "ON" : "OFF"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function MappingsPanel() {
  return (
    <div style={{ marginTop: 20 }}>
      <Panel title="Identity Mappings" count={18}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, fontSize: 13 }}>
          {[
            { tg: "@alice_tg", ds: "selfbot-alice", group: "Crypto Signals" },
            { tg: "@bob_tg", ds: "selfbot-bob", group: "Dev Chat" },
            { tg: "@carol_tg", ds: "selfbot-carol", group: "VIP Lounge" },
            { tg: "@dave_tg", ds: "selfbot-dave", group: "Crypto Signals" },
            { tg: "@eve_tg", ds: "selfbot-eve", group: "Dev Chat" },
            { tg: "@frank_tg", ds: "selfbot-frank", group: "VIP Lounge" },
            { tg: "@grace_tg", ds: "selfbot-grace", group: "Crypto Signals" },
            { tg: "@hank_tg", ds: "selfbot-hank", group: "Dev Chat" },
          ].map((m, i) => (
            <div key={i} style={{ padding: 8, borderRadius: 6, background: "#1a1a1a", border: "1px solid #2a2a2a" }}>
              <div style={{ color: "#8af", fontSize: 12 }}>{m.tg}</div>
              <div style={{ fontSize: 11, color: "#aaa" }}>→ {m.ds}</div>
              <div style={{ fontSize: 10, color: "#666", marginTop: 2 }}>{m.group}</div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function LogPanel() {
  return (
    <div style={{ marginTop: 20 }}>
      <Panel title="Recent Events" count={0}>
        <div style={{ maxHeight: 200, overflowY: "auto", fontSize: 12, fontFamily: "monospace" }}>
          {[
            "[12:34:05] sync: alice → selfbot-alice avatar updated",
            "[12:33:58] sync: bob → selfbot-bob nickname set",
            "[12:33:12] fwd: [Crypto Signals] @alice_tg: BTC looks bullish today",
            "[12:32:45] role: selfbot-alice +VIP in guild",
            "[12:30:00] sync cycle complete: 18/18 accounts synced",
          ].map((line, i) => (
            <div key={i} style={{ padding: "3px 0", borderBottom: "1px solid #1a1a1a", color: "#aaa" }}>
              {line}
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function Panel({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <div style={{ borderRadius: 8, background: "#141414", border: "1px solid #222", overflow: "hidden" }}>
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid #222",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span style={{ fontWeight: 600 }}>{title}</span>
        <span style={{ fontSize: 12, color: "#888" }}>{count}</span>
      </div>
      <div style={{ padding: 16 }}>{children}</div>
    </div>
  );
}
