"use client";

import { useEffect, useState } from "react";
import { api } from "../../../lib/api";

export default function SettingsPage() {
  const [business, setBusiness] = useState(null);
  const [ai, setAi] = useState(null);
  const [wa, setWa] = useState(null);
  const [sub, setSub] = useState(null);
  const [waForm, setWaForm] = useState({ phone_number_id: "", display_phone: "" });
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/api/business").then(setBusiness).catch((e) => setError(e.message));
    api.get("/api/business/ai-settings").then(setAi);
    api.get("/api/business/whatsapp").then((s) => {
      setWa(s);
      setWaForm({ phone_number_id: s.phone_number_id || "", display_phone: s.display_phone || "" });
    });
    api.get("/api/subscription").then(setSub);
  }, []);

  async function saveBusiness(e) {
    e.preventDefault();
    setError(""); setMsg("");
    try {
      const { id, slug, status, ...patch } = { ...business };
      patch.settings = business.settings;
      await api.patch("/api/business", patch);
      setMsg("Business profile saved.");
    } catch (e2) { setError(e2.message); }
  }

  async function saveAi(e) {
    e.preventDefault();
    setError(""); setMsg("");
    try {
      await api.patch("/api/business/ai-settings", ai);
      setMsg("AI settings saved.");
    } catch (e2) { setError(e2.message); }
  }

  async function connectWa(e) {
    e.preventDefault();
    setError(""); setMsg("");
    try {
      const s = await api.post("/api/business/whatsapp/connect", waForm);
      setWa(s);
      setMsg("WhatsApp account connected. Webhook URL: /api/webhooks/whatsapp");
    } catch (e2) { setError(e2.message); }
  }

  async function changePlan(plan) {
    try {
      setSub({ ...sub, ...(await api.post(`/api/subscription/checkout?plan=${plan}`)) });
      setMsg(`Plan changed to ${plan}.`);
    } catch (e2) { setError(e2.message); }
  }

  if (!business || !ai) return <p className="text-gray-500">Loading…</p>;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold mb-1">Settings</h1>
        <p className="text-sm text-gray-500">Business profile, WhatsApp connection, AI behavior and plan.</p>
      </div>

      {msg && <p className="text-sm text-emerald-700 bg-emerald-50 rounded-lg p-3">{msg}</p>}
      {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg p-3">{error}</p>}

      <Card title="WhatsApp connection">
        <form onSubmit={connectWa} className="space-y-3">
          <p className="text-xs text-gray-500">
            Connect your official WhatsApp Cloud API phone number. Point the Meta webhook to
            <code className="mx-1 bg-gray-100 px-1.5 py-0.5 rounded font-mono">/api/webhooks/whatsapp</code>
            and set the verify token from your .env.
          </p>
          <div className="flex gap-3 flex-wrap">
            <input required value={waForm.phone_number_id} onChange={(e) => setWaForm({ ...waForm, phone_number_id: e.target.value })}
              placeholder="Phone Number ID (from Meta dashboard)"
              className="flex-1 min-w-64 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            <input value={waForm.display_phone} onChange={(e) => setWaForm({ ...waForm, display_phone: e.target.value })}
              placeholder="+92 300 0000000"
              className="w-56 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            <button type="submit" className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm hover:bg-emerald-700">
              {wa?.status === "connected" ? "Update" : "Connect"}
            </button>
          </div>
          {wa && (
            <p className="text-xs text-gray-500">
              Status: <span className="font-medium">{wa.status}</span>
              {wa.display_phone ? ` · ${wa.display_phone}` : ""}
            </p>
          )}
        </form>
      </Card>

      <Card title="AI agent">
        <form onSubmit={saveAi} className="grid md:grid-cols-2 gap-4">
          <Field label="Agent name"><input value={ai.agent_name} onChange={(e) => setAi({ ...ai, agent_name: e.target.value })} className={inputCls} /></Field>
          <Field label="Tone"><input value={ai.tone} onChange={(e) => setAi({ ...ai, tone: e.target.value })} className={inputCls} /></Field>
          <div className="md:col-span-2">
            <Field label="Greeting message ({business} is auto-replaced)">
              <textarea rows={2} value={ai.greeting} onChange={(e) => setAi({ ...ai, greeting: e.target.value })} className={inputCls} />
            </Field>
          </div>
          <div className="md:col-span-2">
            <Field label="Business instructions for the AI">
              <textarea rows={3} value={ai.instructions} onChange={(e) => setAi({ ...ai, instructions: e.target.value })} className={inputCls} />
            </Field>
          </div>
          <Field label="Handoff keywords (comma-separated)">
            <input value={ai.handoff_keywords} onChange={(e) => setAi({ ...ai, handoff_keywords: e.target.value })} className={inputCls} />
          </Field>
          <Field label="Supported languages">
            <input value={ai.supported_languages} onChange={(e) => setAi({ ...ai, supported_languages: e.target.value })} className={inputCls} />
          </Field>
          <div className="md:col-span-2">
            <button type="submit" className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm hover:bg-emerald-700">Save AI settings</button>
          </div>
        </form>
      </Card>

      <Card title="Business profile">
        <form onSubmit={saveBusiness} className="grid md:grid-cols-2 gap-4">
          <Field label="Name"><input value={business.name} onChange={(e) => setBusiness({ ...business, name: e.target.value })} className={inputCls} /></Field>
          <Field label="Phone"><input value={business.phone} onChange={(e) => setBusiness({ ...business, phone: e.target.value })} className={inputCls} /></Field>
          <div className="md:col-span-2">
            <Field label="Address"><input value={business.address} onChange={(e) => setBusiness({ ...business, address: e.target.value })} className={inputCls} /></Field>
          </div>
          <div className="md:col-span-2">
            <Field label="Description"><textarea rows={2} value={business.description} onChange={(e) => setBusiness({ ...business, description: e.target.value })} className={inputCls} /></Field>
          </div>
          <div className="md:col-span-2">
            <Field label="Settings JSON (hours, delivery, booking capacity)">
              <textarea rows={4} value={JSON.stringify(business.settings, null, 2)}
                onChange={(e) => { try { setBusiness({ ...business, settings: JSON.parse(e.target.value) }); setError(""); } catch { setError("Settings must be valid JSON"); } }}
                className={`${inputCls} font-mono text-xs`} />
            </Field>
          </div>
          <div className="md:col-span-2">
            <button type="submit" className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm hover:bg-emerald-700">Save profile</button>
          </div>
        </form>
      </Card>

      {sub && (
        <Card title="Subscription">
          <div className="flex items-center gap-6 flex-wrap">
            <div>
              <div className="text-sm">Current plan: <span className="font-semibold capitalize">{sub.plan}</span> ({sub.status})</div>
              <div className="text-xs text-gray-500 mt-1">
                AI messages this month: {sub.usage.ai_messages || 0} / {sub.limits.ai_messages_per_month.toLocaleString()}
              </div>
            </div>
            <div className="flex gap-2">
              {["starter", "business", "pro"].map((p) => (
                <button key={p} onClick={() => changePlan(p)} disabled={sub.plan === p}
                  className={`text-xs px-3 py-1.5 rounded-lg border capitalize ${
                    sub.plan === p ? "bg-emerald-600 text-white border-emerald-600" : "bg-white border-gray-300 hover:border-emerald-400"
                  }`}>
                  {p}
                </button>
              ))}
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

const inputCls = "mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500";

function Card({ title, children }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <h2 className="text-sm font-semibold text-gray-700 mb-4">{title}</h2>
      {children}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block text-xs font-medium text-gray-600">
      {label}
      {children}
    </label>
  );
}
