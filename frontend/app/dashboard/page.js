"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../../lib/api";

export default function OverviewPage() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/api/analytics?days=30").then(setStats).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="text-red-600">{error}</p>;
  if (!stats) return <p className="text-gray-500">Loading analytics…</p>;

  const cards = [
    { label: "Conversations", value: stats.conversations },
    { label: "AI Resolution", value: `${stats.resolution_rate}%` },
    { label: "Human Handoffs", value: stats.human_handoffs },
    { label: "AI Messages", value: stats.ai_messages },
    { label: "Orders", value: stats.orders },
    { label: "Revenue", value: `PKR ${stats.revenue.toLocaleString()}` },
    { label: "Bookings", value: stats.bookings },
    { label: "New Customers", value: stats.new_customers },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Overview</h1>
      <p className="text-sm text-gray-500 mb-6">Last {stats.period_days} days</p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {cards.map((c) => (
          <div key={c.label} className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="text-xs text-gray-500">{c.label}</div>
            <div className="text-xl font-semibold mt-1">{c.value}</div>
          </div>
        ))}
      </div>

      <div className="grid md:grid-cols-2 gap-6 mb-8">
        <ChartCard title="Orders & Revenue by day">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={stats.orders_by_day}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="date" fontSize={11} />
              <YAxis fontSize={11} />
              <Tooltip />
              <Bar dataKey="count" name="Orders" fill="#059669" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Messages by day">
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={stats.messages_by_day}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="date" fontSize={11} />
              <YAxis fontSize={11} />
              <Tooltip />
              <Line type="monotone" dataKey="count" name="Messages" stroke="#059669" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <ChartCard title="Popular items">
        {stats.popular_items.length === 0 ? (
          <p className="text-sm text-gray-500">No orders yet.</p>
        ) : (
          <div className="space-y-2">
            {stats.popular_items.map((item) => {
              const max = stats.popular_items[0].qty || 1;
              return (
                <div key={item.name} className="flex items-center gap-3 text-sm">
                  <span className="w-44 truncate">{item.name}</span>
                  <div className="flex-1 bg-gray-100 rounded-full h-2.5">
                    <div
                      className="bg-emerald-600 h-2.5 rounded-full"
                      style={{ width: `${(item.qty / max) * 100}%` }}
                    />
                  </div>
                  <span className="w-10 text-right text-gray-600">{item.qty}</span>
                </div>
              );
            })}
          </div>
        )}
      </ChartCard>
    </div>
  );
}

function ChartCard({ title, children }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <h2 className="text-sm font-semibold text-gray-700 mb-3">{title}</h2>
      {children}
    </div>
  );
}
