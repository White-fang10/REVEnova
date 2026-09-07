"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Briefcase, ArrowRight } from "lucide-react";
import { api } from "@/lib/client";
import { formatINR } from "@/lib/format";
import { Card, Skeleton } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

type CaseRow = {
  id: number;
  case_code: string;
  status: string;
  revenue_at_risk: number;
  recovery_probability: number;
  root_cause: string | null;
  leak_type: string | null;
  customer: string | null;
  failure_reason: string | null;
  recommended_strategy: string | null;
  created_at: string | null;
};

const STATUSES = [
  { v: "", l: "All" },
  { v: "open", l: "Open" },
  { v: "approved", l: "Approved" },
  { v: "recovered", l: "Recovered" },
  { v: "escalated", l: "Escalated" },
  { v: "stopped", l: "Stopped" },
  { v: "closed", l: "Closed" },
];

export default function CasesPage() {
  const [cases, setCases] = useState<CaseRow[] | null>(null);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    setCases(null);
    api<CaseRow[]>(`/cases?limit=80${status ? `&status=${status}` : ""}`)
      .then(setCases)
      .catch(() => {});
  }, [status]);

  const filtered = (cases ?? []).filter(
    (c) =>
      !search ||
      c.case_code?.toLowerCase().includes(search.toLowerCase()) ||
      c.customer?.toLowerCase().includes(search.toLowerCase()) ||
      c.failure_reason?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div>
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-paper md:text-3xl">
          <Briefcase size={26} className="text-gold" />
          Recovery Cases
        </h1>
        <p className="mt-1 text-sm text-muted">
          Open a case to inspect diagnosis, candidate strategies, and the agent
          execution trace.
        </p>
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1.5">
          {STATUSES.map(({ v, l }) => (
            <button
              key={v}
              onClick={() => setStatus(v)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                status === v
                  ? "border-gold bg-gold/15 text-gold"
                  : "border-ink-edge text-muted hover:text-paper"
              }`}
            >
              {l}
            </button>
          ))}
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search case / customer / reason…"
          className="ml-auto w-64 rounded-lg border border-ink-edge bg-ink-card px-3 py-1.5 text-sm text-paper placeholder-muted outline-none focus:border-gold/50"
        />
      </div>

      {!cases ? (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card className="text-center text-sm text-muted">
          No cases match this filter.
        </Card>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-ink-edge">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-ink-edge bg-ink-deep/60 text-left text-xs uppercase tracking-wider text-muted">
                <th className="px-4 py-3 font-medium">Case</th>
                <th className="px-4 py-3 font-medium">Customer</th>
                <th className="px-4 py-3 text-right font-medium">At risk</th>
                <th className="px-4 py-3 text-right font-medium">Recovery %</th>
                <th className="px-4 py-3 font-medium">Reason</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr
                  key={c.id}
                  className="border-b border-ink-edge/50 text-paper transition-colors hover:bg-gold/5"
                >
                  <td className="px-4 py-3">
                    <span className="mono font-semibold text-gold">
                      {c.case_code}
                    </span>
                    <div className="text-[11px] text-muted">{c.leak_type}</div>
                  </td>
                  <td className="px-4 py-3">{c.customer ?? "—"}</td>
                  <td className="mono px-4 py-3 text-right font-semibold">
                    {formatINR(c.revenue_at_risk)}
                  </td>
                  <td className="mono px-4 py-3 text-right text-gold">
                    {((c.recovery_probability ?? 0) * 100).toFixed(0)}%
                  </td>
                  <td className="max-w-[180px] truncate px-4 py-3 text-muted">
                    {c.failure_reason ?? c.root_cause ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    <Badge status={c.status} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/cases/${c.id}`}
                      className="inline-flex items-center gap-1 text-gold hover:text-gold-light"
                    >
                      Open <ArrowRight size={14} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
