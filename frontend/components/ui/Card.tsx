"use client";

import { cls } from "@/lib/format";

export function Card({
  children,
  className = "",
  lift = false,
}: {
  children: React.ReactNode;
  className?: string;
  lift?: boolean;
}) {
  return (
    <div
      className={cls(
        "rounded-2xl border border-ink-edge bg-ink-card/70 p-5",
        lift && "lift-card",
        className
      )}
    >
      {children}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={cls("skeleton", className)} />;
}
