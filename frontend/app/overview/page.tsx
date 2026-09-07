"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Briefcase, TrendingUp } from "lucide-react";
import { api } from "@/lib/client";
import { formatINR } from "@/lib/format";
import type { Summary } from "@/lib/types";
import { Card, Skeleton } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { Badge } from "@/components/ui/Badge";

export default function OverviewPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [activeCases, setActiveCases] = useState<any[] | null>(null);

  useEffect(() => {
    api<Summary>("/dashboard/summary").then(setSummary).catch(() => {});
    api<any[]>("/cases?status=open&limit=6")
      .then(setActiveCases)
      .catch(() => {});
  }, []);

  return (
    <div className="relative">
      <div className="hero-aura" />
      <div className="bg-grid pointer-events-none absolute inset-0" />

      <div className="relative">
        {/* Page intro */}
        <div className="mb-8">
          <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-gold">
            <span className="live-dot" />
            Autonomous Revenue Recovery · Live
          </div>
          <h1 className="text-2xl font-bold text-paper md:text-3xl">
            Revenue Recovery Overview
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            DETECT → DIAGNOSE → DECIDE → RECOVER → MEASURE → LEARN. AI reasons;
            deterministic code enforces every money decision.
          </p>
        </div>

        {/* Hero stat cards */}
        {!summary ? (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Card key={i}>
                <Skeleton className="h-3 w-20" />
                <Skeleton className="mt-4 h-8 w-28" />
                <Skeleton className="mt-4 h-3 w-16" />
              </Card>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
            <StatCard
              label="Revenue at Risk"
              value={summary.revenue_at_risk}
              kind="money"
              compact
              live
              hint="Lifetime"
            />
            <StatCard
              label="Predicted Recovery"
              value={summary.predicted_recovery}
              kind="money"
              compact
              hint="Model estimate"
            />
            <StatCard
              label="Actual Recovery"
              value={summary.actual_recovery}
              kind="money"
              compact
              hint="Measured"
            />
            <StatCard
              label="Recovery Rate"
              value={summary.recovery_rate}
              kind="pct"
              hint="Actual / at risk"
            />
            <StatCard
              label="Active Cases"
              value={summary.active_cases}
              kind="int"
              hint="Open + approved"
            />
          </div>
        )}

        {/* Case pipeline strip */}
        <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {summary && (
            <>
              {[
                { k: "total", l: "Total Cases" },
                { k: "open", l: "Open" },
                { k: "recovered", l: "Recovered" },
                { k: "escalated", l: "Escalated" },
                { k: "closed", l: "Closed" },
                { k: "stopped", l: "Stopped" },
              ].map(({ k, l }) => (
                <Card key={k} className="!p-4 text-center">
                  <div className="mono text-2xl font-bold text-paper">
                    {summary.case_counts?.[k as keyof typeof summary.case_counts] ?? 0}
                  </div>
                  <div className="mt-1 text-xs uppercase tracking-wide text-muted">
                    {l}
                  </div>
                </Card>
              ))}
            </>
          )}
        </div>

        {/* Active cases quick list */}
        <div className="mt-10">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-lg font-semibold text-paper">
              <Briefcase size={18} className="text-gold" />
              Active Recovery Cases
            </h2>
            <Link
              href="/cases"
              className="group flex items-center gap-1 text-sm font-medium text-gold hover:text-gold-light"
            >
              View all
              <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" />
            </Link>
          </div>

          {!activeCases ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="rounded-2xl border border-ink-edge p-4">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="mt-2 h-3 w-64" />
                </div>
              ))}
            </div>
          ) : activeCases.length === 0 ? (
            <Card className="text-center text-sm text-muted">
              No open cases — revenue is flowing cleanly.
            </Card>
          ) : (
            <div className="space-y-3">
              {activeCases.map((c) => (
                <Link href={`/cases/${c.id}`} key={c.id}>
                  <Card lift className="flex flex-wrap items-center justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="mono font-semibold text-gold">
                          {c.case_code}
                        </span>
                        <Badge status={c.status} />
                      </div>
                      <div className="mt-1 truncate text-sm text-muted">
                        {c.customer ?? "—"} · {c.leak_type} ·{" "}
                        {c.failure_reason ?? "unknown reason"}
                      </div>
                      {c.root_cause && (
                        <div className="mt-1 text-xs text-muted">
                          Root cause: {c.root_cause}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-6 text-right">
                      <div>
                        <div className="text-xs uppercase text-muted">At risk</div>
                        <div className="mono font-semibold text-paper">
                          {formatINR(c.revenue_at_risk)}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs uppercase text-muted">Recovery prob</div>
                        <div className="mono font-semibold text-gold">
                          {((c.recovery_probability ?? 0) * 100).toFixed(0)}%
                        </div>
                      </div>
                      <TrendingUp size={18} className="text-muted" />
                    </div>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
