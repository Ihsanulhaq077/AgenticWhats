"use client";

import { useEffect, useState } from "react";
import { api } from "../../../lib/api";

const FLOW = ["pending", "confirmed", "preparing", "ready", "out_for_delivery", "delivered"];

export default function OrdersPage() {
  const [orders, setOrders] = useState([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");

  async function load(f) {
    try {
      setOrders(await api.get(`/api/orders${f ? `?status_filter=${f}` : ""}`));
    } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(""); }, []);

  async function setStatus(id, status) {
    await api.patch(`/api/orders/${id}`, { status });
    await load(filter);
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Orders</h1>
      {error && <p className="text-red-600 mb-4">{error}</p>}

      <div className="flex gap-2 mb-5 flex-wrap">
        {["", ...FLOW, "cancelled"].map((s) => (
          <button
            key={s || "all"}
            onClick={() => { setFilter(s); load(s); }}
            className={`text-xs px-3 py-1.5 rounded-full border transition ${
              filter === s ? "bg-emerald-600 text-white border-emerald-600" : "bg-white border-gray-300 hover:border-emerald-400"
            }`}
          >
            {s || "All"}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {orders.map((o) => (
          <div key={o.id} className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-start justify-between flex-wrap gap-3">
              <div>
                <div className="font-semibold text-sm">
                  Order #{o.id}
                  <span className={`ml-2 text-[10px] px-2 py-0.5 rounded-full font-medium ${
                    o.status === "cancelled" ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-800"
                  }`}>{o.status.replace(/_/g, " ")}</span>
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  {o.items.map((i) => `${i.qty}× ${i.name}`).join(", ")}
                </div>
                {o.delivery_address && (
                  <div className="text-xs text-gray-400 mt-0.5">📍 {o.delivery_address}</div>
                )}
                <div className="text-xs text-gray-400">
                  {new Date(o.created_at).toLocaleString()}
                </div>
              </div>
              <div className="text-right">
                <div className="font-semibold text-sm">PKR {o.total.toLocaleString()}</div>
                <div className="text-[10px] text-gray-400">
                  subtotal {o.subtotal.toLocaleString()} + delivery {o.delivery_fee.toLocaleString()}
                </div>
                {o.status !== "delivered" && o.status !== "cancelled" && (
                  <select
                    value=""
                    onChange={(e) => e.target.value && setStatus(o.id, e.target.value)}
                    className="mt-2 text-xs border border-gray-300 rounded-lg px-2 py-1"
                  >
                    <option value="">Move to…</option>
                    {FLOW.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
                    <option value="cancelled">cancelled</option>
                  </select>
                )}
              </div>
            </div>
          </div>
        ))}
        {orders.length === 0 && <p className="text-sm text-gray-500">No orders{filter ? ` with status "${filter}"` : " yet"}.</p>}
      </div>
    </div>
  );
}
