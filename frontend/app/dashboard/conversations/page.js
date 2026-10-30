"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../../lib/api";

const STATUS_STYLES = {
  ai: "bg-emerald-100 text-emerald-800",
  needs_human: "bg-red-100 text-red-700",
  human: "bg-amber-100 text-amber-800",
  closed: "bg-gray-100 text-gray-500",
};

export default function ConversationsPage() {
  const [list, setList] = useState([]);
  const [selected, setSelected] = useState(null);
  const [search, setSearch] = useState("");
  const [reply, setReply] = useState("");
  const [error, setError] = useState("");
  const bottomRef = useRef(null);

  const load = useCallback(async (q) => {
    try {
      const data = await api.get(`/api/conversations${q ? `?q=${encodeURIComponent(q)}` : ""}`);
      setList(data);
      return data;
    } catch (e) {
      setError(e.message);
      return [];
    }
  }, []);

  useEffect(() => { load(""); }, [load]);

  async function open(conv) {
    setSelected(conv);
    const detail = await api.get(`/api/conversations/${conv.id}`);
    setSelected(detail);
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  }

  async function sendReply(e) {
    e.preventDefault();
    if (!reply.trim() || !selected) return;
    await api.post(`/api/conversations/${selected.id}/reply`, { content: reply });
    setReply("");
    await open({ id: selected.id });
    await load(search);
  }

  async function takeover() {
    await api.post(`/api/conversations/${selected.id}/takeover`);
    await open({ id: selected.id });
    await load(search);
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Conversations</h1>
      {error && <p className="text-red-600 mb-4">{error}</p>}

      <div className="flex gap-6">
        <div className="w-80 shrink-0">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load(search)}
            placeholder="Search name / number…"
            className="w-full mb-3 rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
          <div className="space-y-2 max-h-[70vh] overflow-y-auto">
            {list.map((c) => (
              <button
                key={c.id}
                onClick={() => open(c)}
                className={`w-full text-left rounded-xl border p-3 transition ${
                  selected?.id === c.id ? "border-emerald-500 bg-emerald-50" : "border-gray-200 bg-white hover:border-emerald-300"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{c.customer_name || c.customer_number}</span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${STATUS_STYLES[c.status] || ""}`}>
                    {c.status.replace("_", " ")}
                  </span>
                </div>
                <div className="text-xs text-gray-500 truncate mt-1">{c.last_message_preview || "—"}</div>
              </button>
            ))}
            {list.length === 0 && <p className="text-sm text-gray-500 p-3">No conversations yet. Send a WhatsApp message via the webhook simulator.</p>}
          </div>
        </div>

        <div className="flex-1 flex flex-col bg-white rounded-xl border border-gray-200 h-[70vh]">
          {!selected ? (
            <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
              Select a conversation
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
                <div>
                  <div className="text-sm font-semibold">{selected.customer?.name}</div>
                  <div className="text-xs text-gray-500">{selected.customer?.whatsapp_number} · {selected.customer?.language}</div>
                </div>
                <div className="flex gap-2">
                  {selected.status === "needs_human" && (
                    <button onClick={takeover} className="text-xs px-3 py-1.5 rounded-lg bg-amber-500 text-white hover:bg-amber-600">
                      Accept handoff
                    </button>
                  )}
                  {selected.status !== "closed" && (
                    <button
                      onClick={async () => { await api.post(`/api/conversations/${selected.id}/close`); await open({ id: selected.id }); await load(search); }}
                      className="text-xs px-3 py-1.5 rounded-lg bg-gray-200 hover:bg-gray-300"
                    >
                      Close
                    </button>
                  )}
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-2">
                {selected.messages.map((m) => (
                  <div key={m.id} className={`flex ${m.direction === "inbound" ? "justify-start" : "justify-end"}`}>
                    <div
                      className={`max-w-[75%] rounded-2xl px-3.5 py-2 text-sm whitespace-pre-wrap ${
                        m.message_type === "system"
                          ? "bg-gray-100 text-gray-500 text-xs"
                          : m.direction === "inbound"
                          ? "bg-gray-100"
                          : m.ai_generated
                          ? "bg-emerald-600 text-white"
                          : "bg-emerald-900 text-white"
                      }`}
                    >
                      {m.content}
                      <div className="text-[10px] opacity-60 mt-1">
                        {m.ai_generated ? "🤖 AI" : m.direction === "inbound" ? "" : "👤 Staff"} ·{" "}
                        {new Date(m.created_at).toLocaleTimeString()}
                      </div>
                    </div>
                  </div>
                ))}
                <div ref={bottomRef} />
              </div>

              <form onSubmit={sendReply} className="flex gap-2 p-3 border-t border-gray-100">
                <input
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  placeholder="Reply as staff (sends via WhatsApp)…"
                  className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm"
                />
                <button type="submit" className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm hover:bg-emerald-700">
                  Send
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
