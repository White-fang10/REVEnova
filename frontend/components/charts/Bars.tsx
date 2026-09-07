"use client";

import { useEffect, useState } from "react";
import { cls } from "@/lib/format";

/** Animated horizontal bars (grow from zero) for the strategy simulator. */
export function HBar({
  value,
  max,
  label,
  sublabel,
  highlighted = false,
  suffix = "",
}: {
  value: number;
  max: number;
  label: string;
  sublabel?: string;
  highlighted?: boolean;
  suffix?: string;
}) {
  const [pct, setPct] = useState(0);
  useEffect(() => {
    const t = requestAnimationFrame(() => setPct(max > 0 ? value / max : 0));
    return () => cancelAnimationFrame(t);
  }, [value, max]);

  const display = `${label}${suffix || ""}`;
  return (
    <div className="w-full">
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span
          className={cls(
            "text-sm font-medium",
            highlighted ? "text-gold" : "text-paper"
          )}
        >
          {display}
        </span>
        {sublabel && <span className="mono text-xs text-muted">{sublabel}</span>}
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-ink-edge">
        <div
          className={cls(
            "h-full rounded-full transition-[width] duration-1000 ease-out",
            highlighted
              ? "bg-gradient-to-r from-gold to-gold-light shadow-[0_0_12px_rgba(245,158,11,0.7)]"
              : "bg-gold/50"
          )}
          style={{ width: `${pct * 100}%` }}
        />
      </div>
    </div>
  );
}

/** Animated donut chart with a center label. */
export function Donut({
  data,
  size = 200,
}: {
  data: { label: string; value: number; color: string }[];
  size?: number;
}) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const stroke = 16;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  let offset = 0;

  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const t = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(t);
  }, []);

  // aggregate colours as plain CSS colors (already hex/approved)
  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#1C2430"
          strokeWidth={stroke}
        />
        {data.map((d, i) => {
          const frac = d.value / total;
          const dash = mounted ? frac * c : 0;
          const dashOffset = mounted ? -offset * c : 0;
          offset += frac;
          return (
            <circle
              key={i}
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={d.color}
              strokeWidth={stroke}
              strokeDasharray={`${dash} ${c - dash}`}
              strokeDashoffset={dashOffset}
              strokeLinecap="butt"
              className="transition-[stroke-dasharray,stroke-dashoffset] duration-1000 ease-out"
            />
          );
        })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="mono text-2xl font-bold text-paper">
          {data.length}
        </span>
        <span className="text-xs uppercase tracking-wider text-muted">
          leak types
        </span>
      </div>
    </div>
  );
}
