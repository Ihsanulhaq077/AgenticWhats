"use client";

import { useEffect, useState } from "react";
import { api } from "../../../lib/api";

export default function MenuPage() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ name: "", description: "", price: "", availability: true });
  const [error, setError] = useState("");

  async function load() {
    try { setItems(await api.get("/api/menu")); } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, []);

  async function addItem(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/api/menu", { ...form, price: Number(form.price) });
      setForm({ name: "", description: "", price: "", availability: true });
      await load();
    } catch (e2) { setError(e2.message); }
  }

  async function toggle(item) {
    await api.patch(`/api/menu/${item.id}`, { availability: !item.availability });
    await load();
  }

  async function remove(id) {
    await api.delete(`/api/menu/${id}`);
    await load();
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Menu</h1>

      <form onSubmit={addItem} className="bg-white rounded-xl border border-gray-200 p-4 mb-6 flex gap-3 flex-wrap items-end">
        <label className="text-xs font-medium text-gray-600 flex-1 min-w-40">
          Name
          <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" placeholder="Chicken Biryani" />
        </label>
        <label className="text-xs font-medium text-gray-600 flex-1 min-w-40">
          Description
          <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" placeholder="Spicy basmati rice…" />
        </label>
        <label className="text-xs font-medium text-gray-600 w-28">
          Price (PKR)
          <input required type="number" min="0" step="0.01" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })}
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" placeholder="450" />
        </label>
        <button type="submit" className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm hover:bg-emerald-700">
          Add item
        </button>
      </form>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
        {items.map((item) => (
          <div key={item.id} className="flex items-center justify-between p-4">
            <div className="flex-1">
              <div className="text-sm font-medium flex items-center gap-2">
                {item.name}
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                  item.availability ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-700"
                }`}>
                  {item.availability ? "available" : "unavailable"}
                </span>
              </div>
              {item.description && <div className="text-xs text-gray-500 mt-0.5">{item.description}</div>}
            </div>
            <div className="text-sm font-semibold w-24 text-right">PKR {item.price.toLocaleString()}</div>
            <div className="flex gap-2 ml-4">
              <button onClick={() => toggle(item)} className="text-xs px-3 py-1.5 rounded-lg bg-gray-100 hover:bg-gray-200">
                {item.availability ? "Mark unavailable" : "Mark available"}
              </button>
              <button onClick={() => remove(item.id)} className="text-xs px-3 py-1.5 rounded-lg bg-red-50 text-red-600 hover:bg-red-100">
                Delete
              </button>
            </div>
          </div>
        ))}
        {items.length === 0 && <p className="text-sm text-gray-500 p-4">No menu items yet.</p>}
      </div>
    </div>
  );
}
