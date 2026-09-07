"use client";

import { useEffect, useState } from "react";
import { Droplets, AlertTriangle, ArrowRight } from "lucide-react";
import { api } from "@/lib/client";
import { formatINR, formatPct } from "@/lib/format";
import type { LeakBucket, DetectedLeak } from "@/lib/types";
import { Card, Skeleton } from "@/components/ui/Card";
import { Donut, HBar } from "@/components/charts/Bars";

const DONUT_COLORS = [
  "#F59E0B",
  "#FBBF24",
  "#B45309",
  "#FDE68A",
  "#92400E",
];

export default function LeaksPage() {
  const [breakdown, setBreakdown] = useState<LeakBucket[] | null>(null);
  const [detected, setDetected] = useState<DetectedLeak[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    api<{ breakdown: LeakBucket[]; detected: DetectedLeak[] }>("/leaks")
      .then((r) => {
        setBreakdown(r.breakdown);
        setDetected(r.detected);
      })
      .catch(() => {});
  }, []);

  const maxBucket = breakdown?.length
    ? Math.max(...breakdown.map((b) => b.revenue_at_risk), 1)
    : 1;

  const donutData = (breakdown ?? []).map((b, i) => ({
    label: b.type,
    value: b.revenue_at_risk,
    color: DONUT_COLORS[i % DONUT_COLORS.length],
  }));

  const selectedBucket = breakdown?.find((b) => b.type === selected) ?? null;

  return (
    <div>
      <div className="mb-8">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-paper md:text-3xl">
          <Droplets size={26} className="text-gold" />
          Revenue Leak Explorer
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Statistical anomaly detection across cohorts — z-score deviation vs.
          a 30-day baseline. Click a leak type to drill down.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Breakdown bars */}
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
              Leak breakdown
            </h2>
            <span className="text-xs text-muted">
              {breakdown?.reduce((s, b) => s + b.cases, 0) ?? "—"} active cases
            </span>
          </div>
          {!breakdown ? (
            <div className="space-y-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-6 w-full" />
              ))}
            </div>
          ) : breakdown.length === 0 ? (
            <div className="text-sm text-muted">No active leaks detected.</div>
          ) : (
            <div className="space-y-4">
              {breakdown.map((b) => (
                <button
                  key={b.type}
                  onClick={() => setSelected(b.type)}
                  className="group block w-full rounded-lg p-2 text-left transition-colors hover:bg-gold/5"
                >
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2 font-medium text-paper group-hover:text-gold">
                      {b.type}
                      <span className="rounded-full bg-ink-edge px-1.5 text-[11px] text-muted">
                        {b.cases}
                      </span>
                    </span>
                    <span className="mono font-semibold text-gold">
                      {formatINR(b.revenue_at_risk)}
                    </span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-ink-edge">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-gold to-gold-light transition-[width] duration-1000 ease-out"
                      style={{
                        width: `${(b.revenue_at_risk / maxBucket) * 100}%`,
                      }}
                    />
                  </div>
                </button>
              ))}
            </div>
          )}
        </Card>

        {/* Donut */}
        <Card className="flex flex-col items-center justify-center">
          <h2 className="mb-4 self-start text-sm font-semibold uppercase tracking-wider text-muted">
            Share by type
          </h2>
          {breakdown ? (
            <Donut data={donutData} size={220} />
          ) : (
            <Skeleton className="h-[220px] w-[220px] rounded-full" />
          )}
          <div className="mt-5 flex flex-wrap justify-center gap-3">
            {donutData.map((d, i) => (
              <button
                key={i}
                onClick={() => setSelected(d.label)}
                className="flex items-center gap-1.5 text-xs text-muted hover:text-paper"
              >
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ background: d.color }}
                />
                {d.label}
              </button>
            ))}
          </div>
        </Card>
      </div>

      {/* Selected bucket detail */}
      {selectedBucket && (
        <Card className="mt-6 border-gold/20" lift>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="flex items-center gap-2 font-semibold text-paper">
              <ArrowRight size={16} className="text-gold" />
              {selected}
            </h3>
            <button
              onClick={() => setSelected(null)}
              className="text-xs text-muted hover:text-paper"
            >
              Close
            </button>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <div className="text-xs uppercase text-muted">Cases</div>
              <div className="mono text-lg font-bold text-paper">
                {selectedBucket.cases}
              </div>
            </div>
            <div>
              <div className="text-xs uppercase text-muted">Revenue at risk</div>
              <div className="mono text-lg font-bold text-gold">
                {formatINR(selectedBucket.revenue_at_risk)}
              </div>
            </div>
            <div>
              <div className="text-xs uppercase text-muted">Predicted recovery</div>
              <div className="mono text-lg font-bold text-gold">
                {formatINR(selectedBucket.predicted_recovery)}
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Detected anomalies */}
      <div className="mt-8">
        <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-paper">
          <AlertTriangle size={18} className="text-gold" />
          Detected statistical anomalies
        </h2>
        {!detected ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-20 w-full" />
            ))}
          </div>
        ) : detected.length === 0 ? (
          <Card className="text-center text-sm text-muted">
            No anomalies above the z-score threshold.
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {detected.map((d, i) => (
              <Card key={i} lift className="border-gold/15">
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-sm font-semibold text-paper">
                    {d.dimension}: <span className="text-gold">{d.value}</span>
                  </span>
                  <span
                    className={`mono rounded-full px-2 py-0.5 text-xs font-bold ${
                      d.zscore >= 3
                        ? "bg-danger/15 text-danger"
                        : "bg-gold/15 text-gold"
                    }`}
                  >
                    z={d.zscore.toFixed(1)}
                  </span>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted">Current failure rate</span>
                    <span className="mono font-semibold text-paper">
                      {formatPct(d.current_rate)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">Baseline (30d)</span>
                    <span className="mono font-semibold text-muted">
                      {formatPct(d.baseline_rate)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">Δ</span>
                    <span className="mono font-semibold text-danger">
                      +{(d.delta_pts * 100).toFixed(1)} pts
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">Affected txn / revenue</span>
                    <span className="mono font-semibold text-gold">
                      {d.affected_count} · {formatINR(d.revenue_at_risk)}
                    </span>
                  </div>
                </div>
                <div className="mt-3">
                  <HBar
                    value={d.current_rate}
                    max={Math.max(d.baseline_rate * 2, d.current_rate, 0.01)}
                    label="failure rate"
                    highlighted
                  />
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
