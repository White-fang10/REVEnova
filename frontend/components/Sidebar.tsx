"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Droplets,
  Briefcase,
  FlaskConical,
  ScrollText,
  Zap,
} from "lucide-react";
import { cls } from "@/lib/format";

const NAV = [
  { href: "/overview", label: "Executive Overview", icon: LayoutDashboard },
  { href: "/leaks", label: "Revenue Leak Explorer", icon: Droplets },
  { href: "/cases", label: "Recovery Cases", icon: Briefcase },
  { href: "/simulator", label: "Strategy Simulator", icon: FlaskConical },
  { href: "/audit", label: "Audit & Learning Log", icon: ScrollText },
];

export default function Sidebar() {
  const pathname = usePathname();

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);

  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col border-r border-ink-edge bg-ink-deep/90 backdrop-blur md:flex">
      <div className="flex items-center gap-3 px-6 py-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-gold to-gold-light shadow-[0_0_20px_-2px_rgba(245,158,11,0.6)]">
          <Zap size={22} className="text-ink" strokeWidth={2.5} />
        </div>
        <div className="leading-tight">
          <div className="font-mono text-lg font-bold tracking-tight text-paper">
            REV<span className="text-gold">Enova</span>
          </div>
          <div className="text-[11px] uppercase tracking-widest text-muted">
            Recovery Intelligence
          </div>
        </div>
      </div>

      <nav className="mt-2 flex-1 space-y-1 px-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = isActive(href);
          return (
            <Link
              key={href}
              href={href}
              className={cls(
                "group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200",
                active
                  ? "bg-gold/10 text-gold"
                  : "text-muted hover:bg-white/5 hover:text-paper"
              )}
            >
              {active && (
                <span className="absolute left-0 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r bg-gradient-to-b from-gold to-gold-light shadow-[0_0_12px_rgba(245,158,11,0.8)]" />
              )}
              <Icon
                size={18}
                className={cls(
                  "transition-colors",
                  active ? "text-gold" : "text-muted group-hover:text-paper"
                )}
              />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="mx-3 mb-4 rounded-xl border border-gold/10 bg-gold/5 p-4">
        <div className="mb-1 flex items-center gap-2 text-xs uppercase tracking-wider text-muted">
          <span className="live-dot" /> Engine Status
        </div>
        <div className="font-mono text-sm font-semibold text-gold">
          DETECT → LEARN
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-muted">
          Closed-loop pipeline. Deterministic policy engine enforces all money
          rules.
        </p>
      </div>
    </aside>
  );
}
