"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import type { Summary } from "@/lib/types";
import { formatINR, formatPct } from "@/lib/format";

export default function TopBar() {
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api<Summary>("/dashboard/summary")
        .then((s) => alive && setSummary(s))
        .catch(() => {});
    load();
    const id = setInterval(load, 8000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const items = summary
    ? [
        { label: "Revenue at Risk", value: formatINR(summary.revenue_at_risk, true) },
        { label: "Predicted Recovery", value: formatINR(summary.predicted_recovery, true) },
        { label: "Actual Recovery", value: formatINR(summary.actual_recovery, true) },
        { label: "Recovery Rate", value: formatPct(summary.recovery_rate) },
        { label: "Active Cases", value: String(summary.active_cases) },
        { label: "Open Cases", value: String(summary.case_counts?.open ?? 0) },
        { label: "Recovered", value: String(summary.case_counts?.recovered ?? 0) },
      ]
    : [];

  // duplicate the list for a seamless loop
  const loop = [...items, ...items];

  return (
    <header className="sticky top-0 z-30 border-b border-ink-edge bg-ink/85 backdrop-blur">
      <div className="flex h-14 items-center gap-4 px-4 md:px-6">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted">
          <span className="live-dot" />
          <span className="hidden sm:inline">Live</span>
        </div>

        <div className="relative flex-1 overflow-hidden">
          {items.length > 0 ? (
            <div className="ticker-track">
              {loop.map((it, i) => (
                <span
                  key={i}
                  className="mx-6 inline-flex items-baseline gap-2 font-mono text-sm"
                >
                  <span className="text-muted">{it.label}:</span>
                  <span className="font-semibold text-gold">{it.value}</span>
                  <span className="mx-2 text-muted/30">•</span>
                </span>
              ))}
            </div>
          ) : (
            <div className="text-sm text-muted">
              Loading live revenue ticker…
            </div>
          )}
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden rounded-lg border border-gold/20 bg-gold/5 px-3 py-1.5 text-xs text-gold sm:block">
            {summary ? formatINR(summary.active_revenue_at_risk, true) : "—"}{" "}
            active
          </div>
        </div>
      </div>
    </header>
  );
}
