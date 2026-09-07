"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Cpu, Check, Shield, Search } from "lucide-react";
import { cls } from "@/lib/format";
import type { CaseDetail } from "@/lib/types";

const TOOL_ICON: Record<string, React.ReactNode> = {
  get_customer: <Search size={14} />,
  get_transaction: <Search size={14} />,
  get_payment_history: <Search size={14} />,
  get_failure_details: <Search size={14} />,
  get_recovery_history: <Search size={14} />,
  check_policy: <Shield size={14} />,
  calculate_recovery_score: <Cpu size={14} />,
};

/** Animated agent trace: tool calls light up sequentially (from dashboard trace). */
export default function AgentTrace({ trace }: { trace: CaseDetail["trace"] }) {
  const rows = (trace ?? []).slice().reverse(); // old → new
  const [visible, setVisible] = useState(0);

  useEffect(() => {
    setVisible(0);
    if (!rows.length) return;
    const id = setInterval(() => {
      setVisible((v) => {
        if (v >= rows.length) {
          clearInterval(id);
          return v;
        }
        return v + 1;
      });
    }, 420);
    return () => clearInterval(id);
  }, [rows.length]);

  if (!rows.length) {
    return (
      <div className="rounded-xl border border-ink-edge bg-ink-deep/60 p-6 text-center text-sm text-muted">
        No execution trace recorded yet for this case.
      </div>
    );
  }

  return (
    <div className="space-y-0">
      {rows.slice(0, visible).map((row, i) => {
        const isLast = i === visible - 1;
        return (
          <div key={i} className="relative flex gap-3 pb-4 last:pb-0">
            {i < visible - 1 && (
              <span className="absolute left-[13px] top-7 h-full w-px bg-gold/20" />
            )}
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              className={cls(
                "relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg",
                isLast
                  ? "bg-gradient-to-br from-gold to-gold-light text-ink shadow-[0_0_10px_rgba(245,158,11,0.6)]"
                  : "border border-gold/30 bg-gold/10 text-gold"
              )}
            >
              {TOOL_ICON[row.policy_checked] || TOOL_ICON[row.action] || (
                <Check size={14} />
              )}
            </motion.div>
            <div className="min-w-0 flex-1 rounded-r-lg border-l-2 border-gold/30 bg-ink-card/40 px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="mono text-xs font-semibold text-gold">
                  {row.policy_checked || row.action || "agent"}
                </span>
                <span className="text-[11px] text-muted">
                  {row.decision}
                </span>
                {row.amount > 0 && (
                  <span className="mono ml-auto text-xs font-semibold text-paper">
                    ₹{row.amount.toLocaleString("en-IN")}
                  </span>
                )}
              </div>
              {row.reason && (
                <div className="mt-1 text-xs leading-relaxed text-muted">
                  {row.reason}
                </div>
              )}
              {row.policy_checked && (
                <span className="mt-1 inline-block rounded bg-gold/5 px-1.5 py-0.5 text-[10px] text-gold">
                  policy: {row.policy_checked}
                </span>
              )}
            </div>
          </div>
        );
      })}
      {visible < rows.length && (
        <div className="flex gap-3">
          <div className="w-7 shrink-0" />
          <span className="typing-cursor text-xs text-gold/70">
            agent thinking…
          </span>
        </div>
      )}
    </div>
  );
}
