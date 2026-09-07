"use client";

import { useEffect, useRef, useState } from "react";

/** Animated count-up to a target value (handles currency & percentages). */
export function useCountUp(target: number, decimals = 0, duration = 1400) {
  const [value, setValue] = useState(0);
  const prevTarget = useRef(target);

  useEffect(() => {
    const from = prevTarget.current;
    const to = target;
    prevTarget.current = to;
    if (from === to) {
      setValue(to);
      return;
    }
    const start = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(from + (to - from) * eased);
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);

  return Number(value.toFixed(decimals));
}

export function CountUpMoney({
  value,
  compact = false,
  className = "",
}: {
  value: number;
  compact?: boolean;
  className?: string;
}) {
  const v = useCountUp(value, 0);
  const abs = Math.abs(v);
  let text: string;
  if (compact && abs >= 1_00_00_000) text = `₹${(v / 1_00_00_000).toFixed(1)}Cr`;
  else if (compact && abs >= 1_00_000) text = `₹${(v / 1_00_000).toFixed(1)}L`;
  else if (compact && abs >= 1_000) text = `₹${(v / 1_000).toFixed(1)}k`;
  else text = `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  return <span className={`mono ${className}`}>{text}</span>;
}

export function CountUpPct({
  value,
  digits = 1,
  className = "",
}: {
  value: number;
  digits?: number;
  className?: string;
}) {
  const v = useCountUp(value * 100, digits);
  return (
    <span className={`mono ${className}`}>
      {v.toFixed(digits)}%
    </span>
  );
}

export function CountUpInt({
  value,
  className = "",
}: {
  value: number;
  className?: string;
}) {
  const v = useCountUp(value, 0);
  return (
    <span className={`mono ${className}`}>
      {Math.round(v).toLocaleString("en-IN")}
    </span>
  );
}
