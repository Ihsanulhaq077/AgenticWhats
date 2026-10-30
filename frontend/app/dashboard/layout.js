"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, clearToken, getToken } from "../../lib/api";

const NAV = [
  { href: "/dashboard", label: "Overview", icon: "📊" },
  { href: "/dashboard/conversations", label: "Conversations", icon: "💬" },
  { href: "/dashboard/orders", label: "Orders", icon: "🧾" },
  { href: "/dashboard/bookings", label: "Bookings", icon: "📅" },
  { href: "/dashboard/menu", label: "Menu", icon: "🍽️" },
  { href: "/dashboard/knowledge", label: "Knowledge Base", icon: "📚" },
  { href: "/dashboard/settings", label: "Settings & AI", icon: "⚙️" },
];

export default function DashboardLayout({ children }) {
  const pathname = usePathname();
  const router = useRouter();
  const [business, setBusiness] = useState(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api.get("/api/business").then(setBusiness).catch(() => {});
  }, [router]);

  return (
    <div className="flex min-h-screen">
      <aside className="w-60 bg-emerald-900 text-emerald-50 flex flex-col shrink-0">
        <div className="px-5 py-5 border-b border-emerald-800">
          <div className="font-bold text-lg">AgenticWhats</div>
          <div className="text-xs text-emerald-300 mt-0.5 truncate">
            {business ? business.name : "…"}
          </div>
        </div>
        <nav className="flex-1 py-3">
          {NAV.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-5 py-2.5 text-sm transition ${
                  active ? "bg-emerald-700 font-medium" : "hover:bg-emerald-800"
                }`}
              >
                <span>{item.icon}</span> {item.label}
              </Link>
            );
          })}
        </nav>
        <button
          onClick={() => { clearToken(); router.push("/login"); }}
          className="px-5 py-4 text-left text-sm text-emerald-300 hover:text-white border-t border-emerald-800"
        >
          ⏻ Log out
        </button>
      </aside>
      <main className="flex-1 p-8 max-w-6xl">{children}</main>
    </div>
  );
}
