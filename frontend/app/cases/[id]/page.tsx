"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Check,
  ShieldAlert,
  RefreshCw,
  UserCheck,
  CreditCard,
  MonitorSmartphone,
} from "lucide-react";
import { api, post } from "@/lib/client";
import { formatINR, formatPct, cls } from "@/lib/format";
import type { CaseDetail, Strategy } from "@/lib/types";
import { Card, Skeleton } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { StatCard } from "@/components/ui/StatCard";
import { HBar } from "@/components/charts/Bars";
import AgentTrace from "@/components/AgentTrace";

export default function CaseDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = Number(params?.id);

  const [caseData, setCaseData] = useState<CaseDetail | null>(null);
  const [loadingAction, setLoadingAction] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = () => {
    api<CaseDetail>(`/cases/${id}`).then(setCaseData).catch(() => {});
  };

  useEffect(() => {
    setCaseData(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const runCase = async () => {
    setLoadingAction(true);
    await post(`/cases/${id}/run`).catch(() => {});
    load();
    setLoadingAction(false);
  };

  const approve = async () => {
    setBusy(true);
    await post<{ result: any }>(`/cases/${id}/approve`).catch(() => {});
    load();
    setBusy(false);
  };

  const escalate = async () => {
    setBusy(true);
    await post(`/cases/${id}/escalate`).catch(() => {});
    load();
    setBusy(false);
  };

  if (!caseData) {
    return (
      <div>
        <Skeleton className="mb-6 h-8 w-64" />
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-1">
            <Skeleton className="h-64 w-full" />
          </div>
          <div className="lg:col-span-2">
            <Skeleton className="h-64 w-full" />
          </div>
        </div>
      </div>
    );
  }

  const c = caseData;
  const best = c.strategies?.find((s) => s.recommended);

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6 flex items-center gap-3">
        <button
          onClick={() => router.push("/cases")}
          className="text-muted transition-colors hover:text-paper"
        >
          <ArrowLeft size={20} />
        </button>
        <h1 className="flex items-center gap-3 text-2xl font-bold text-paper">
          <span className="mono text-gold">{c.case_code}</span>
          <Badge status={c.status} />
        </h1>
      </div>

      {/* Summary strip */}
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Revenue at risk" value={c.revenue_at_risk} kind="money" live />
        <StatCard label="Recovery probability" value={c.recovery_probability} kind="pct" />
        <StatCard label="Confidence" value={c.confidence} kind="pct" />
        <div className="flex flex-col justify-center gap-2">
          <button
            onClick={runCase}
            disabled={loadingAction}
            className="btn-gold inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm disabled:opacity-50"
          >
            <RefreshCw size={16} className={cls(loadingAction && "animate-spin")} />
            Run Agent Loop
          </button>
          <div className="flex gap-2">
            <button
              onClick={approve}
              disabled={busy || c.status === "recovered"}
              className="btn-ghost inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-sm disabled:opacity-40"
            >
              <Check size={15} /> Approve
            </button>
            <button
              onClick={escalate}
              disabled={busy}
              className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-danger/40 px-3 py-2 text-sm text-danger transition-colors hover:bg-danger/10 disabled:opacity-40"
            >
              <ShieldAlert size={15} /> Escalate
            </button>
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left: diagnosis */}
        <div className="space-y-6 lg:col-span-1">
          <Card>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted">
              Diagnosis
            </h2>
            <div className="mb-3 text-sm uppercase text-muted">
              {c.leak_type}
            </div>
            <p className="mb-3 text-sm leading-relaxed text-paper">
              {c.root_cause || "No diagnosis available yet."}
            </p>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="text-muted">Confidence</span>
              <span className="mono font-semibold text-gold">
                {formatPct(c.confidence)}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-edge">
              <div
                className="h-full rounded-full bg-gradient-to-r from-gold to-gold-light"
                style={{ width: `${c.confidence * 100}%` }}
              />
            </div>
          </Card>

          <Card>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted">
              Customer
            </h2>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gold/10 text-gold">
                <UserCheck size={18} />
              </div>
              <div>
                <div className="font-semibold text-paper">
                  {c.customer?.name ?? "—"}
                </div>
                <div className="text-xs text-muted">
                  {c.customer?.segment ?? "—"} segment
                </div>
              </div>
            </div>
            <div className="mt-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted">Lifetime value</span>
                <span className="mono font-semibold text-paper">
                  {formatINR(c.customer?.lifetime_value ?? 0)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Default method</span>
                <span className="font-medium text-paper">
                  {c.customer?.payment_method ?? "—"}
                </span>
              </div>
            </div>
          </Card>

          <Card>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted">
              Transaction
            </h2>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted">Reference</span>
                <span className="mono text-paper">
                  {c.transaction?.transaction_ref ?? "—"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Amount</span>
                <span className="mono font-semibold text-gold">
                  {formatINR(c.transaction?.amount ?? c.revenue_at_risk)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted">Failed reason</span>
                <span className="font-medium text-danger">
                  {c.transaction?.failure_reason ?? "—"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted">Method / device</span>
                <span className="flex items-center gap-1 font-medium text-paper">
                  <CreditCard size={13} className="text-muted" />
                  {c.transaction?.payment_method ?? "—"}
                  <MonitorSmartphone size={13} className="ml-1 text-muted" />
                  {c.transaction?.device ?? "—"}
                </span>
              </div>
            </div>
          </Card>
        </div>

        {/* Right: strategies + trace */}
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-muted">
              Recommended strategy
            </h2>
            {best ? (
              <div className="rounded-xl border border-gold/30 bg-gold/5 p-5">
                <div className="flex items-center justify-between">
                  <span className="text-lg font-semibold text-gold">
                    {best.name ?? best.key}
                  </span>
                  <span className="mono rounded-full bg-gold/15 px-2 py-0.5 text-xs font-bold text-gold">
                    Recommended
                  </span>
                </div>
                <p className="mt-2 text-sm text-paper">
                  Expected value ₹{(best.expected_value ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                  {" · "}Recovery {formatPct(best.predicted_recovery)}
                  {" · "}Cost ₹{(best.cost ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                </p>
              </div>
            ) : (
              <div className="text-sm text-muted">
                No strategies generated yet. Run the agent loop to generate
                candidates.
              </div>
            )}
          </Card>

          <Card>
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-muted">
              All strategies
            </h2>
            <div className="space-y-4">
              {c.strategies?.map((s) => (
                <StrategyRow key={s.id ?? s.key} s={s} />
              ))}
              {(!c.strategies || c.strategies.length === 0) && (
                <div className="text-sm text-muted">
                  No strategies yet. Run the agent loop.
                </div>
              )}
            </div>
          </Card>

          <Card>
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-muted">
              Agent reasoning trace
            </h2>
            <AgentTrace trace={c.trace} />
          </Card>
        </div>
      </div>
    </div>
  );
}

function StrategyRow({ s }: { s: Strategy }) {
  const highlighted = s.recommended;
  return (
    <div
      className={cls(
        "rounded-xl border p-4 transition-all",
        highlighted ? "border-gold/40 bg-gold/5" : "border-ink-edge"
      )}
    >
      <div className="mb-2 flex items-center justify-between">
        <span
          className={cls(
            "text-sm font-semibold",
            highlighted ? "text-gold" : "text-paper"
          )}
        >
          {s.name ?? s.key}
        </span>
        <span className="text-xs text-muted">
          cost tier: {s.cost_tier ?? "—"}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div className="flex h-9 items-end">
          <HBar
            value={s.predicted_recovery}
            max={1}
            label=""
            sublabel={formatPct(s.predicted_recovery)}
            highlighted={highlighted}
          />
        </div>
        <div>
          <div className="text-xs text-muted">Cost</div>
          <div className="mono text-sm font-semibold text-paper">
            ₹{(s.intervention_cost ?? 0).toLocaleString("en-IN")}
          </div>
        </div>
        <div>
          <div className="text-xs text-muted">Expected value</div>
          <div className="mono text-sm font-semibold text-gold">
            ₹{(s.expected_value ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
          </div>
        </div>
      </div>
    </div>
  );
}
