"use client";

import { useEffect, useState } from "react";
import { api } from "../../../lib/api";

export default function BookingsPage() {
  const [bookings, setBookings] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/api/bookings").then(setBookings).catch((e) => setError(e.message));
  }, []);

  async function cancel(id) {
    await api.patch(`/api/bookings/${id}/cancel`);
    setBookings(await api.get("/api/bookings"));
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Bookings</h1>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      <div className="grid md:grid-cols-2 gap-4">
        {bookings.map((b) => (
          <div key={b.id} className="bg-white rounded-xl border border-gray-200 p-4 flex justify-between">
            <div>
              <div className="font-semibold text-sm">
                Booking #{b.id}
                <span className={`ml-2 text-[10px] px-2 py-0.5 rounded-full font-medium ${
                  b.status === "cancelled" ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-800"
                }`}>{b.status}</span>
              </div>
              <div className="text-sm mt-1">
                📅 {b.date} at {b.time} · {b.party_size} {b.booking_type === "table" ? "guests" : b.booking_type}
              </div>
              {b.notes && <div className="text-xs text-gray-500 mt-1">{b.notes}</div>}
              <div className="text-xs text-gray-400 mt-1">{new Date(b.created_at).toLocaleString()}</div>
            </div>
            {b.status === "confirmed" && (
              <button onClick={() => cancel(b.id)} className="self-start text-xs px-3 py-1.5 rounded-lg bg-red-50 text-red-600 hover:bg-red-100">
                Cancel
              </button>
            )}
          </div>
        ))}
        {bookings.length === 0 && <p className="text-sm text-gray-500">No bookings yet.</p>}
      </div>
    </div>
  );
}
