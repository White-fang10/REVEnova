export const formatINR = (n: number, compact = false): string => {
  const abs = Math.abs(n);
  if (compact && abs >= 1_00_00_000) return `₹${(n / 1_00_00_000).toFixed(1)}Cr`;
  if (compact && abs >= 1_00_000) return `₹${(n / 1_00_000).toFixed(1)}L`;
  if (compact && abs >= 1_000) return `₹${(n / 1_000).toFixed(1)}k`;
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
};

export const formatPct = (p: number, digits = 1): string =>
  `${(p * 100).toFixed(digits)}%`;

export const formatAmountFull = (n: number): string =>
  `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

export const cls = (...parts: Array<string | false | null | undefined>): string =>
  parts.filter(Boolean).join(" ");
