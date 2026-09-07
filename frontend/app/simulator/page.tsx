"use client";

import { useEffect, useState } from "react";
import { FlaskConical, Sparkles, ShieldCheck } from "lucide-react";
import { api } from "@/lib/client";
import { formatINR, formatPct, cls } from "@/lib/format";
import { Card, Skeleton } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

type CaseRow = { id: number; case_code: string; revenue_at_risk: number; status: string };

type StratRes = {
  case: { id: number; case_code: string; revenue_at_risk: number };
  equation: {
    formula: string;
    values: {
      revenue_at_risk: number;
      intervention_costs: Record<string, number>;
      friction_costs: Record<string, number>;
    };
  };
  strategies: {
    key: string;
    name: string;
    predicted_recovery: number;
    cost: number;
    friction_score: number;
    expected_value: number;
    recommended: boolean;
  }[];
  best: [string, number] | [null, 0];
};

export default function SimulatorPage() {
  const [cases, setCases] = useState<CaseRow[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [result, setResult] = useState<StratRes | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api<CaseRow[]>("/cases?limit=100").then(setCases).catch(() => {});
  }, []);

  useEffect(() => {
    if (selectedId == null) return;
    setLoading(true);
    setResult(null);
    api<StratRes>(`/cases/${selectedId}/strategies`)
      .then(setResult)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [selectedId]);

  const maxEV = result?.strategies.length
    ? Math.max(...result.strategies.map((s) => s.expected_value), 1)
    : 1;

  return (
    <div>
      <div className="mb-8">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-paper md:text-3xl">
          <FlaskConical size={26} className="text-gold" />
          Strategy Simulator
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Compare all candidate recovery strategies under a deterministic
          expected-value formula. The highest EV wins — not the highest raw
          probability.
        </p>
      </div>

      {/* Case selector */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <label className="text-sm text-muted">Select case:</label>
        <select
          value={selectedId ?? ""}
          onChange={(e) => setSelectedId(Number(e.target.value))}
          className="rounded-lg border border-ink-edge bg-ink-card px-3 py-2 text-sm text-paper outline-none focus:border-gold/50"
        >
          <option value="" disabled>
            Choose a recovery case…
          </option>
          {cases.map((c) => (
            <option key={c.id} value={c.id}>
              {c.case_code} · {formatINR(c.revenue_at_risk)} · {c.status}
            </option>
          ))}
        </select>
      </div>

      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      )}

      {result && (
        <>
          {/* Equation banner */}
          <Card className="mb-6 border-gold/20">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-gold">
              <Sparkles size={14} /> Expected-Value Equation
            </div>
            <p className="mono text-sm text-paper">{result.equation.formula}</p>
            <div className="mt-2 text-xs text-muted">
              Revenue at risk:{" "}
              <span className="mono text-gold">
                {formatINR(result.equation.values.revenue_at_risk)}
              </span>
            </div>
          </Card>

          {/* Strategy comparison */}
          <div className="overflow-hidden rounded-2xl border border-ink-edge">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ink-edge bg-ink-deep/60 text-left text-xs uppercase tracking-wider text-muted">
                  <th className="px-4 py-3 font-medium">Strategy</th>
                  <th className="px-4 py-3 text-right font-medium">Recovery %</th>
                  <th className="px-4 py-3 text-right font-medium">Cost</th>
                  <th className="px-4 py-3 text-right font-medium">Friction</th>
                  <th className="px-4 py-3 text-right font-medium">Expected value</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {result.strategies.map((s) => {
                  const rec = s.recommended;
                  return (
                    <tr
                      key={s.key}
                      className={cls(
                        "border-b border-ink-edge/50",
                        rec ? "bg-gold/10" : "hover:bg-white/5"
                      )}
                    >
                      <td className="px-4 py-4">
                        <div className="flex items-center gap-2">
                          <span
                            className={cls(
                              "font-medium",
                              rec ? "text-gold" : "text-paper"
                            )}
                          >
                            {s.name}
                          </span>
                          {rec && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-gold px-2 py-0.5 text-[10px] font-bold text-ink">
                              <Sparkles size={10} /> BEST
                            </span>
                          )}
                        </div>
                        <div className="mt-2 h-1.5 w-40 overflow-hidden rounded-full bg-ink-edge">
                          <div
                            className={cls(
                              "h-full rounded-full transition-[width] duration-700 ease-out",
                              rec
                                ? "bg-gradient-to-r from-gold to-gold-light shadow-[0_0_10px_rgba(245,158,11,0.6)]"
                                : "bg-gold/40"
                            )}
                            style={{
                              width: `${(s.expected_value / maxEV) * 100}%`,
                            }}
                          />
                        </div>
                      </td>
                      <td className="mono px-4 py-4 text-right font-semibold text-paper">
                        {formatPct(s.predicted_recovery)}
                      </td>
                      <td className="mono px-4 py-4 text-right text-muted">
                        {formatINR(s.cost)}
                      </td>
                      <td className="mono px-4 py-4 text-right text-muted">
                        {formatINR(s.friction_score)}
                      </td>
                      <td className="mono px-4 py-4 text-right text-lg font-bold text-gold">
                        {formatINR(s.expected_value)}
                      </td>
                      <td className="pr-4 text-right">
                        <ShieldCheck size={16} className={rec ? "text-gold" : "text-muted/40"} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {result.best[0] && (
            <div className="mt-6">
              <Card lift className="border-gold/30">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <div className="text-xs uppercase tracking-wider text-muted">
                      Recommended strategy
                    </div>
                    <div className="mt-1 text-xl font-bold text-gold">
                      {result.best[0]}
                    </div>
                    <div className="mt-1 text-sm text-muted">
                      Highest expected value, not highest probability — balances
                      recovery against intervention and customer friction cost.
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs uppercase tracking-wider text-muted">
                      Expected value
                    </div>
                    <div className="mono text-2xl font-bold text-paper">
                      {formatINR(result.best[1])}
                    </div>
                  </div>
                </div>
              </Card>
            </div>
          )}
        </>
      )}

      {!loading && !result && selectedId == null && (
        <Card className="text-center text-sm text-muted">
          Select a case above to compare its candidate strategies.
        </Card>
      )}

      {!loading && selectedId != null && !result && (
        <Card className="text-center text-sm text-muted">
          No strategies available for this case yet.
        </Card>
      )}
    </div>
  );
}
