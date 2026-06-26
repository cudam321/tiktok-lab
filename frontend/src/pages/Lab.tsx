import { useEffect, useState } from "react";
import {
  api,
  type Account,
  type ExperimentResponse,
  type ExperimentComparison,
  type ExperimentStatusType,
} from "@/lib/api";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from "recharts";
import EmptyState from "@/components/EmptyState";
import {
  FlaskConical,
  Plus,
  Play,
  CheckCircle2,
  Trash2,
  BarChart3,
  X,
  ChevronDown,
  AlertCircle,
} from "lucide-react";

function statusBadge(status: ExperimentStatusType) {
  const map: Record<ExperimentStatusType, { bg: string; text: string }> = {
    draft: { bg: "bg-gray-700", text: "text-gray-300" },
    running: { bg: "bg-blue-400/10", text: "text-blue-400" },
    paused: { bg: "bg-yellow-400/10", text: "text-yellow-400" },
    completed: { bg: "bg-emerald-400/10", text: "text-emerald-400" },
    cancelled: { bg: "bg-red-400/10", text: "text-red-400" },
  };
  const s = map[status] || map.draft;
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${s.bg} ${s.text}`}>
      {status}
    </span>
  );
}

export default function Lab() {
  const [experiments, setExperiments] = useState<ExperimentResponse[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [selectedExp, setSelectedExp] = useState<number | null>(null);
  const [comparison, setComparison] = useState<ExperimentComparison | null>(null);
  const [comparingId, setComparingId] = useState<number | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [exps, accts] = await Promise.all([
        api.getExperiments(),
        api.getAccounts(),
      ]);
      setExperiments(exps);
      setAccounts(accts.accounts);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleCompare(expId: number) {
    setComparingId(expId);
    setSelectedExp(expId);
    try {
      const result = await api.compareExperiment(expId);
      setComparison(result);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Comparison failed");
    } finally {
      setComparingId(null);
    }
  }

  async function handleAction(action: () => Promise<unknown>) {
    try {
      await action();
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Action failed");
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Lab</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Variable insights + A/B testing
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            <Plus size={16} />
            New Experiment
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-gray-500 text-center py-12 animate-pulse">Loading...</div>
      ) : (
        <>
          {/* Experiments */}
          {(
            <>
              {experiments.length === 0 ? (
                <EmptyState
                  icon={<FlaskConical size={48} />}
                  title="No experiments yet"
                  description="Create your first A/B test to learn what variables drive virality."
                  action={
                    <button
                      onClick={() => setShowCreate(true)}
                      className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                    >
                      <Plus size={16} />
                      New Experiment
                    </button>
                  }
                />
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {experiments.map((exp) => (
                    <div
                      key={exp.id}
                      className={`bg-gray-900 border rounded-xl p-5 transition-colors ${
                        selectedExp === exp.id
                          ? "border-blue-500"
                          : "border-gray-800 hover:border-gray-700"
                      }`}
                    >
                      <div className="flex items-start justify-between mb-3">
                        <div>
                          <h3 className="font-medium text-white">{exp.name}</h3>
                          <div className="flex items-center gap-2 mt-1">
                            {statusBadge(exp.status)}
                            <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
                              {exp.variable}
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center gap-1">
                          {exp.status === "draft" && (
                            <button
                              onClick={() => handleAction(() => api.startExperiment(exp.id))}
                              className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-blue-400"
                              title="Start"
                            >
                              <Play size={14} />
                            </button>
                          )}
                          {(exp.status === "running" || exp.status === "completed") && (
                            <button
                              onClick={() => handleCompare(exp.id)}
                              disabled={comparingId === exp.id}
                              className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-purple-400"
                              title="Compare Results"
                            >
                              <BarChart3 size={14} />
                            </button>
                          )}
                          {exp.status === "running" && (
                            <button
                              onClick={() => handleAction(() => api.completeExperiment(exp.id))}
                              className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-emerald-400"
                              title="Complete"
                            >
                              <CheckCircle2 size={14} />
                            </button>
                          )}
                          {(exp.status === "draft" || exp.status === "completed" || exp.status === "cancelled") && (
                            <button
                              onClick={() => {
                                if (confirm("Delete this experiment?"))
                                  handleAction(() => api.deleteExperiment(exp.id));
                              }}
                              className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-red-400"
                              title="Delete"
                            >
                              <Trash2 size={14} />
                            </button>
                          )}
                        </div>
                      </div>

                      {exp.hypothesis && (
                        <p className="text-sm text-gray-400 mb-2 italic">"{exp.hypothesis}"</p>
                      )}

                      <div className="flex items-center gap-4 text-xs text-gray-500">
                        <span>Variants: {exp.variants.join(" vs ")}</span>
                        <span>Target: {exp.metric_target}</span>
                        <span>Min n={exp.min_sample_size}</span>
                      </div>

                      {exp.result_summary && (
                        <div className="mt-3 p-3 rounded-lg bg-gray-800/50 text-sm text-gray-300">
                          {exp.result_summary}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}

      {/* Comparison Results Panel */}
      {comparison && selectedExp && (
        <ComparisonPanel
          comparison={comparison}
          experiment={experiments.find((e) => e.id === selectedExp)!}
          onClose={() => {
            setComparison(null);
            setSelectedExp(null);
          }}
        />
      )}

      {/* Create Modal */}
      {showCreate && (
        <CreateExperimentModal
          accounts={accounts}
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            load();
          }}
        />
      )}
    </div>
  );
}

// --- Variable Leaderboard ---

// --- Comparison Results ---

function ComparisonPanel({
  comparison,
  experiment,
  onClose,
}: {
  comparison: ExperimentComparison;
  experiment: ExperimentResponse;
  onClose: () => void;
}) {
  const variants = Object.entries(comparison.variants);
  const chartData = variants.map(([name, stats]) => ({
    name,
    mean: stats.mean ?? 0,
    n: stats.n,
  }));

  const { bayesian, mann_whitney } = comparison;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white">
          Results: {experiment.name}
        </h3>
        <button onClick={onClose} className="text-gray-500 hover:text-white">
          <X size={20} />
        </button>
      </div>

      <div
        className={`p-4 rounded-lg border ${
          mann_whitney.significant
            ? "bg-emerald-400/5 border-emerald-400/20 text-emerald-300"
            : bayesian.preliminary
            ? "bg-yellow-400/5 border-yellow-400/20 text-yellow-300"
            : "bg-gray-800 border-gray-700 text-gray-300"
        }`}
      >
        <p className="text-sm font-medium">{comparison.conclusion}</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div>
          <h4 className="text-sm text-gray-400 mb-3">Mean {comparison.metric} by Variant</h4>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="name" tick={{ fill: "#9ca3af", fontSize: 12 }} />
              <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#111827",
                  border: "1px solid #374151",
                  borderRadius: "8px",
                  fontSize: "12px",
                }}
              />
              <Bar dataKey="mean" radius={[4, 4, 0, 0]}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill={i === 0 ? "#3b82f6" : "#8b5cf6"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div>
          <h4 className="text-sm text-gray-400 mb-3">Statistics</h4>
          <div className="space-y-3 text-sm">
            {variants.map(([name, stats]) => (
              <div key={name} className="flex items-center justify-between bg-gray-800 rounded-lg px-3 py-2">
                <span className="text-white font-medium">{name}</span>
                <div className="flex gap-4 text-gray-400">
                  <span>n={stats.n}</span>
                  <span>mean={stats.mean?.toFixed(2) ?? "—"}</span>
                  <span>std={stats.std?.toFixed(2) ?? "—"}</span>
                </div>
              </div>
            ))}

            <div className="bg-gray-800 rounded-lg px-3 py-2">
              <div className="text-gray-500 text-xs mb-1">Mann-Whitney U Test</div>
              <div className="flex gap-4 text-gray-300">
                <span>U = {mann_whitney.u_stat ?? "—"}</span>
                <span>z = {mann_whitney.z_score ?? "—"}</span>
                <span>p = {mann_whitney.p_value != null ? mann_whitney.p_value.toFixed(4) : "—"}</span>
                {mann_whitney.significant && (
                  <span className="text-emerald-400 font-medium">Significant</span>
                )}
              </div>
            </div>

            <div className="bg-gray-800 rounded-lg px-3 py-2">
              <div className="flex items-center gap-2 text-gray-500 text-xs mb-1">
                Bayesian Posterior
                {bayesian.preliminary && (
                  <span className="text-yellow-400 flex items-center gap-1">
                    <AlertCircle size={10} /> Preliminary
                  </span>
                )}
              </div>
              <div className="flex gap-4 text-gray-300">
                <span>
                  P(B{">"}A) = {bayesian.prob_b_better != null ? `${(bayesian.prob_b_better * 100).toFixed(1)}%` : "—"}
                </span>
                <span>diff = {bayesian.mean_diff?.toFixed(2) ?? "—"}</span>
                <span>
                  95% CI [{bayesian.ci_lower?.toFixed(2) ?? "—"}, {bayesian.ci_upper?.toFixed(2) ?? "—"}]
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- Create Modal ---

function CreateExperimentModal({
  accounts,
  onClose,
  onCreated,
}: {
  accounts: Account[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [variable, setVariable] = useState("hook_style");
  const [variantA, setVariantA] = useState("");
  const [variantB, setVariantB] = useState("");
  const [hypothesis, setHypothesis] = useState("");
  const [accountId, setAccountId] = useState<number | undefined>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [variables, setVariables] = useState<string[]>([]);

  useEffect(() => {
    api.getExperimentVariables().then((d) => setVariables(d.variables));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name || !variantA || !variantB) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.createExperiment({
        name,
        variable,
        variants: [variantA, variantB],
        hypothesis: hypothesis || undefined,
        account_id: accountId,
      });
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl w-full max-w-lg mx-4 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h2 className="text-lg font-semibold text-white">New Experiment</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1.5">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Question vs Bold Text Hooks"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1.5">Variable</label>
            <div className="relative">
              <select
                value={variable}
                onChange={(e) => setVariable(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white appearance-none focus:outline-none focus:border-blue-500"
              >
                {variables.map((v) => (
                  <option key={v} value={v}>{v.replace(/_/g, " ")}</option>
                ))}
              </select>
              <ChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm text-gray-400 mb-1.5">Variant A</label>
              <input
                value={variantA}
                onChange={(e) => setVariantA(e.target.value)}
                placeholder="e.g., question"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1.5">Variant B</label>
              <input
                value={variantB}
                onChange={(e) => setVariantB(e.target.value)}
                placeholder="e.g., bold_text"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1.5">Hypothesis (optional)</label>
            <textarea
              value={hypothesis}
              onChange={(e) => setHypothesis(e.target.value)}
              rows={2}
              placeholder="e.g., Question hooks drive higher engagement for DJ clips"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 resize-none focus:outline-none focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1.5">Account (optional)</label>
            <div className="relative">
              <select
                value={accountId ?? ""}
                onChange={(e) => setAccountId(e.target.value ? Number(e.target.value) : undefined)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white appearance-none focus:outline-none focus:border-blue-500"
              >
                <option value="">Cross-account</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.display_name}</option>
                ))}
              </select>
              <ChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
            </div>
          </div>

          {error && (
            <div className="text-sm text-red-400 bg-red-400/10 px-3 py-2 rounded-lg">{error}</div>
          )}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2.5 rounded-lg text-sm font-medium text-gray-400 bg-gray-800 hover:bg-gray-700 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !name || !variantA || !variantB}
              className="flex-1 px-4 py-2.5 rounded-lg text-sm font-medium bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? "Creating..." : "Create Experiment"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
