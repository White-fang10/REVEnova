"use client";

import { cls } from "@/lib/format";
import { Card } from "./Card";
import { CountUpInt, CountUpMoney, CountUpPct } from "./counter";

/** Executive stat card — label top-left, large gold value, delta bottom-right. */
export function StatCard({
  label,
  value,
  kind = "money",
  compact = false,
  delta,
  deltaLabel,
  live = false,
  hint,
}: {
  label: string;
  value: number;
  kind?: "money" | "pct" | "int";
  compact?: boolean;
  delta?: number; // delta to show as trend
  deltaLabel?: string;
  live?: boolean;
  hint?: string;
}) {
  const deltaAbs = delta !== undefined ? Math.abs(delta) : undefined;
  return (
    <Card lift className="flex h-full flex-col justify-between">
      <div className="flex items-start justify-between">
        <span className="text-xs uppercase tracking-wider text-muted">
          {label}
        </span>
        {live && <span className="live-dot" />}
      </div>

      <div className="mt-4">
        {kind === "money" && (
          <CountUpMoney
            value={value}
            compact={compact}
            className="text-3xl font-bold text-gold md:text-4xl"
          />
        )}
        {kind === "pct" && (
          <CountUpPct
            value={value}
            className="text-3xl font-bold text-gold md:text-4xl"
          />
        )}
        {kind === "int" && (
          <CountUpInt
            value={value}
            className="text-3xl font-bold text-gold md:text-4xl"
          />
        )}
      </div>

      <div className="mt-4 flex items-center justify-between text-xs">
        {hint ? (
          <span className="text-muted">{hint}</span>
        ) : (
          <span className="text-transparent">_</span>
        )}
        <span
          className={cls(
            "flex items-center gap-1 font-medium",
            delta !== undefined && delta >= 0 ? "text-gold" : "text-muted"
          )}
        >
          {delta !== undefined && (
            <span className="mono">
              {delta >= 0 ? "▲" : "▼"} {deltaAbs?.toFixed(1)}%
            </span>
          )}
          {deltaLabel && <span>{deltaLabel}</span>}
        </span>
      </div>
    </Card>
  );
}
