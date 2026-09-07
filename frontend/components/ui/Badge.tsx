"use client";

import { cls } from "@/lib/format";

export function Badge({
  status,
  className = "",
}: {
  status: string;
  className?: string;
}) {
  return (
    <span
      className={cls(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize",
        statusColorClass(status),
        className
      )}
    >
      {status}
    </span>
  );
}

function statusColorClass(status: string): string {
  switch (status) {
    case "open":
      return "text-gold border-gold/40 bg-gold/5";
    case "approved":
      return "text-gold border-gold/40 bg-gold/10";
    case "recovered":
      return "text-gold border-gold/50 bg-gold/10";
    case "escalated":
      return "text-danger border-danger/40 bg-danger/5";
    case "stopped":
      return "text-danger border-danger/40 bg-danger/5";
    case "closed":
      return "text-muted border-muted/30 bg-muted/5";
    case "success":
      return "text-gold border-gold/40 bg-gold/10";
    case "completed":
      return "text-gold border-gold/40 bg-gold/10";
    default:
      return "text-muted border-muted/30 bg-muted/5";
  }
}
