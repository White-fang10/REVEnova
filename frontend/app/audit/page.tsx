"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ScrollText, Brain, TrendingUp } from "lucide-react";
import { api } from "@/lib/client";
import { formatINR, formatPct, cls } from "@/lib/format";
import type { LearnedEntry } from "@/lib/types";
import { Card, Skeleton } from "@/components/ui/Card";

type AuditRow = {
  id: number;
  case_id: number | null;
  case_code: string | null;
  agent: string;
  decision: string;
  reason: string;
  policy_checked: string;
  action: string;
  amount: number;
  timestamp: string | null;
};

const POLICY_FILTERS = [
  "All",
  "POL-RETRY",
  "POL-DISCOUNT",
  "POL-CONTACT",
  "POL-ESCALATION",
  "POL-PAYMENT-LINK",
  "POL-OFFER",
];

export default function AuditPage() {
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [learned, setLearned] = useState<LearnedEntry[] | null>(null);
  const [policyFilter, setPolicyFilter] = useState("All");
  const [query, setQuery] = useState("");

  useEffect(() => {
    api<AuditRow[]>("/audit").then(setRows).catch(() => {});
    api<{ learned: LearnedEntry[]; context: any }>("/learning")
      .then((r) => setLearned(r.learned))
      .catch(() => {});
  }, []);

  const filtered = useMemo(() => {
    return (rows ?? []).filter((r) => {
      const matchesPolicy =
        policyFilter === "All" || (r.policy_checked ?? "").includes(policyFilter);
      const q = query.toLowerCase();
      const matchesQuery =
        !q ||
        (r.case_code ?? "").toLowerCase().includes(q) ||
        (r.decision ?? "").toLowerCase().includes(q) ||
        (r.action ?? "").toLowerCase().includes(q) ||
        (r.reason ?? "").toLowerCase().includes(q);
      return matchesPolicy && matchesQuery;
    });
  }, [rows, policyFilter, query]);

  const maxLearned = learned?.length
    ? Math.max(...learned.map((l) => l.attempts), 1)
    : 1;

  return (
    <div>
      <div className="mb-8">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-paper md:text-3xl">
          <ScrollText size={26} className="text-gold" />
          Audit & Learning Log
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Chronological AI decision log: what happened, why, which policy was
          checked, which action was taken, and the outcome. Outcomes are
          captured and used to improve future strategy selection.
        </p>
      </div>

      {/* Learning loop */}
      <div className="mb-8">
        <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-paper">
          <Brain size={18} className="text-gold" />
          Learning loop — observed strategy performance
        </h2>
        {!learned ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : learned.length === 0 ? (
          <Card className="text-sm text-muted">
            No recorded outcomes yet. Outcomes captured after the first
            recovery actions will appear here.
          </Card>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-ink-edge">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ink-edge bg-ink-deep/60 text-left text-xs uppercase tracking-wider text-muted">
                  <th className="px-4 py-3 font-medium">Strategy</th>
                  <th className="px-4 py-3 text-right font-medium">Attempts</th>
                  <th className="px-4 py-3 text-right font-medium">Successes</th>
                  <th className="px-4 py-3 text-right font-medium">Recovery rate</th>
                  <th className="px-4 py-3 text-right font-medium">Recovered</th>
                </tr>
              </thead>
              <tbody>
                {learned.map((l, i) => (
                  <tr key={i} className="border-b border-ink-edge/50 hover:bg-gold/5">
                    <td className="px-4 py-3 font-medium text-paper">
                      {l.strategy}
                    </td>
                    <td className="mono px-4 py-3 text-right text-muted">
                      {l.attempts}
                    </td>
                    <td className="mono px-4 py-3 text-right text-muted">
                      {l.successes}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <div className="h-1.5 w-24 overflow-hidden rounded-full bg-ink-edge">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-gold to-gold-light transition-[width] duration-700"
                            style={{ width: `${(l.attempts / maxLearned) * 100}%` }}
                          />
                        </div>
                        <span className="mono font-semibold text-gold">
                          {formatPct(l.recovery_rate)}
                        </span>
                      </div>
                    </td>
                    <td className="mono px-4 py-3 text-right font-semibold text-paper">
                      {formatINR(l.amount_recovered)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Audit log */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-paper">
          <TrendingUp size={18} className="text-gold" />
          Decision log
        </h2>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search decisions…"
            className="w-52 rounded-lg border border-ink-edge bg-ink-card px-3 py-1.5 text-sm text-paper placeholder-muted outline-none focus:border-gold/50"
          />
          <select
            value={policyFilter}
            onChange={(e) => setPolicyFilter(e.target.value)}
            className="rounded-lg border border-ink-edge bg-ink-card px-3 py-1.5 text-sm text-paper outline-none focus:border-gold/50"
          >
            {POLICY_FILTERS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
      </div>

      {!rows ? (
        <div className="space-y-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card className="text-center text-sm text-muted">
          No audit entries match this filter.
        </Card>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-ink-edge">
          <div className="max-h-[640px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-ink-deep">
                <tr className="border-b border-ink-edge text-left text-xs uppercase tracking-wider text-muted">
                  <th className="px-4 py-3 font-medium">Case</th>
                  <th className="px-4 py-3 font-medium">Decision</th>
                  <th className="px-4 py-3 font-medium">Reason</th>
                  <th className="px-4 py-3 font-medium">Policy</th>
                  <th className="px-4 py-3 font-medium">Action</th>
                  <th className="px-4 py-3 text-right font-medium">Amount</th>
                  <th className="px-4 py-3 text-right font-medium">When</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr
                    key={r.id}
                    className="border-b border-ink-edge/50 align-top hover:bg-gold/5"
                  >
                    <td className="px-4 py-3">
                      {r.case_code ? (
                        <Link
                          href={`/cases/${r.case_id}`}
                          className="mono text-gold hover:underline"
                        >
                          {r.case_code}
                        </Link>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-paper">{r.decision}</div>
                      <div className="text-[11px] text-muted">{r.action}</div>
                    </td>
                    <td className="max-w-[220px] px-4 py-3 text-xs leading-relaxed text-muted">
                      {r.reason}
                    </td>
                    <td className="px-4 py-3">
                      {r.policy_checked ? (
                        <span className="rounded bg-gold/10 px-1.5 py-0.5 text-[11px] text-gold">
                          {r.policy_checked}
                        </span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-paper">{r.agent}</td>
                    <td className="mono px-4 py-3 text-right font-semibold text-gold">
                      {r.amount > 0 ? formatINR(r.amount) : "—"}
                    </td>
                    <td className="mono whitespace-nowrap px-4 py-3 text-right text-[11px] text-muted">
                      {r.timestamp ? new Date(r.timestamp).toLocaleString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
