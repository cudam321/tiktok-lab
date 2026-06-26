import { useEffect, useMemo, useState } from "react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import {
  api,
  type CombinedAnalytics as CombinedData,
  type BestTimeResponse,
  type ContentDecayResponse,
} from "@/lib/api";
import { BarChart3, TrendingUp, TrendingDown, Eye, Heart, MessageCircle, Share2, Users, Flame } from "lucide-react";
import EmptyState from "@/components/EmptyState";

type RangeKey = "7" | "30" | "90" | "all";
type MetricKey = "views" | "engagement" | "likes" | "comments" | "shares";
type ChartMode = "cumulative" | "daily";

const RANGES: { key: RangeKey; label: string; days: number }[] = [
  { key: "7", label: "7 days", days: 7 },
  { key: "30", label: "30 days", days: 30 },
  { key: "90", label: "90 days", days: 90 },
  { key: "all", label: "All Time", days: 0 },
];

const METRICS: { key: MetricKey; label: string; color: string }[] = [
  { key: "views", label: "Views", color: "#ef4444" },
  { key: "engagement", label: "Engagement", color: "#f59e0b" },
  { key: "likes", label: "Likes", color: "#ec4899" },
  { key: "comments", label: "Comments", color: "#3b82f6" },
  { key: "shares", label: "Shares", color: "#10b981" },
];

function fmt(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M";
  if (abs >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, "") + "K";
  return n.toLocaleString();
}

function fmtPct(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `${n.toFixed(2)}%`;
}

function fmtSigned(n: number): string {
  if (n === 0) return "0";
  return (n > 0 ? "+" : "") + fmt(n);
}

function fmtDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

interface KpiProps {
  label: string;
  value: string;
  sub?: string;
  icon: React.ReactNode;
  trend?: number;
}

function KpiCard({ label, value, sub, icon, trend }: KpiProps) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs uppercase tracking-wider text-gray-500 font-medium">
          {label}
        </div>
        <div className="text-gray-600">{icon}</div>
      </div>
      <div className="text-2xl font-bold text-white tabular-nums">{value}</div>
      <div className="flex items-center gap-2 mt-1 text-xs">
        {sub && <span className="text-gray-500">{sub}</span>}
        {trend !== undefined && trend !== 0 && (
          <span
            className={`inline-flex items-center gap-0.5 ${
              trend > 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {trend > 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
            {fmtSigned(trend)}
          </span>
        )}
      </div>
    </div>
  );
}

function PanelCard({
  title,
  right,
  children,
  span = 1,
}: {
  title: string;
  right?: React.ReactNode;
  children: React.ReactNode;
  span?: 1 | 2 | 3;
}) {
  const spanClass =
    span === 3 ? "lg:col-span-3" : span === 2 ? "lg:col-span-2" : "";
  return (
    <div className={`bg-gray-900 border border-gray-800 rounded-xl p-5 ${spanClass}`}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-gray-300">{title}</h3>
        {right}
      </div>
      {children}
    </div>
  );
}

export default function CombinedAnalytics() {
  const [range, setRange] = useState<RangeKey>("all");
  const [data, setData] = useState<CombinedData | null>(null);
  const [bestTime, setBestTime] = useState<BestTimeResponse | null>(null);
  const [decay, setDecay] = useState<ContentDecayResponse | null>(null);
  const [decayError, setDecayError] = useState<string | null>(null);
  const [bestTimeError, setBestTimeError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [chartMode, setChartMode] = useState<ChartMode>("cumulative");
  const [metric, setMetric] = useState<MetricKey>("views");

  const days = RANGES.find((r) => r.key === range)?.days ?? 0;

  useEffect(() => {
    setLoading(true);
    api
      .getCombinedAnalytics(days)
      .then(setData)
      .catch((e) => {
        console.error("getCombinedAnalytics failed", e);
        setData(null);
      })
      .finally(() => setLoading(false));
  }, [days]);

  useEffect(() => {
    api
      .getBestTimeToPost()
      .then((r) => {
        setBestTime(r);
        setBestTimeError(null);
      })
      .catch((e) => {
        setBestTimeError(String(e?.message || e));
        setBestTime(null);
      });
    api
      .getContentDecay()
      .then((r) => {
        setDecay(r);
        setDecayError(null);
      })
      .catch((e) => {
        setDecayError(String(e?.message || e));
        setDecay(null);
      });
  }, []);

  const chartData = useMemo(() => {
    if (!data) return [];
    return data.timeseries.map((p) => {
      const rec = p as unknown as Record<string, number | string>;
      return {
        date: fmtDate(p.date),
        raw: p.date,
        value:
          chartMode === "cumulative"
            ? (rec[`${metric}_cumulative`] as number)
            : (rec[`${metric}_daily`] as number),
      };
    });
  }, [data, chartMode, metric]);

  const followerChart = useMemo(() => {
    if (!data) return [];
    return data.followers_timeseries.map((p) => ({
      date: fmtDate(p.date),
      total: p.total,
      delta: p.delta,
    }));
  }, [data]);

  const heatmap = useMemo(() => parseBestTime(bestTime), [bestTime]);
  const decayChart = useMemo(() => parseDecay(decay), [decay]);

  const activeMetric = METRICS.find((m) => m.key === metric)!;

  if (!loading && !data) {
    return (
      <EmptyState
        icon={<BarChart3 size={48} />}
        title="No analytics yet"
        description="Connect accounts and let the poller collect data — metrics refresh every 30 minutes."
      />
    );
  }

  return (
    <div className="space-y-5">
      {/* Range selector */}
      <div className="flex items-center justify-between">
        <div className="inline-flex items-center bg-gray-900 border border-gray-800 rounded-lg p-1">
          {RANGES.map((r) => (
            <button
              key={r.key}
              onClick={() => setRange(r.key)}
              className={`px-3 py-1.5 text-sm rounded-md transition ${
                range === r.key
                  ? "bg-gray-800 text-white"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
        {data?.window.earliest_data && (
          <div className="text-xs text-gray-500">
            Earliest data: {fmtDate(data.window.earliest_data)}
          </div>
        )}
      </div>

      {/* KPI Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
        <KpiCard
          label="Views"
          value={fmt(data?.kpis.views ?? 0)}
          sub={range === "all" ? "All time" : `Last ${days}d`}
          icon={<Eye size={14} />}
        />
        <KpiCard
          label="Engagement"
          value={fmt(data?.kpis.engagement ?? 0)}
          sub={fmtPct(data?.kpis.engagement_rate ?? 0) + " rate"}
          icon={<Flame size={14} />}
        />
        <KpiCard
          label="Likes"
          value={fmt(data?.kpis.likes ?? 0)}
          icon={<Heart size={14} />}
        />
        <KpiCard
          label="Comments"
          value={fmt(data?.kpis.comments ?? 0)}
          icon={<MessageCircle size={14} />}
        />
        <KpiCard
          label="Shares"
          value={fmt(data?.kpis.shares ?? 0)}
          icon={<Share2 size={14} />}
        />
        <KpiCard
          label="Posts"
          value={fmt(data?.kpis.posts ?? 0)}
          sub={range === "all" ? "All time" : "Published"}
          icon={<BarChart3 size={14} />}
        />
        <KpiCard
          label="Followers"
          value={fmt(data?.kpis.followers.current ?? 0)}
          icon={<Users size={14} />}
          trend={data?.kpis.followers.delta}
        />
        <KpiCard
          label="Net Growth"
          value={fmtSigned(data?.kpis.followers.delta ?? 0)}
          sub={
            (data?.kpis.followers.gained ?? 0) > 0
              ? `+${fmt(data!.kpis.followers.gained)} / -${fmt(data!.kpis.followers.lost)}`
              : undefined
          }
          icon={<TrendingUp size={14} />}
        />
      </div>

      {/* All-time strip — small, secondary */}
      {data && (
        <div className="text-xs text-gray-500 flex flex-wrap gap-x-6 gap-y-1 px-1">
          <span>
            <span className="text-gray-400">All-time views:</span>{" "}
            <span className="text-white tabular-nums">{fmt(data.kpis.alltime.views)}</span>
          </span>
          <span>
            <span className="text-gray-400">All-time engagement:</span>{" "}
            <span className="text-white tabular-nums">{fmt(data.kpis.alltime.engagement)}</span>{" "}
            ({fmtPct(data.kpis.alltime.engagement_rate)})
          </span>
          <span>
            <span className="text-gray-400">All-time likes:</span>{" "}
            <span className="text-white tabular-nums">{fmt(data.kpis.alltime.likes)}</span>
          </span>
          <span className="text-gray-600">·</span>
          <span className="text-gray-600">
            Saves not exposed by TikTok API
          </span>
        </div>
      )}

      {/* Main chart */}
      <PanelCard
        title="Performance over time"
        right={
          <div className="flex items-center gap-2">
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value as MetricKey)}
              className="bg-gray-950 border border-gray-700 rounded-md px-2 py-1 text-xs text-white focus:outline-none"
            >
              {METRICS.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
            <div className="inline-flex items-center bg-gray-950 border border-gray-700 rounded-md p-0.5">
              <button
                onClick={() => setChartMode("daily")}
                className={`px-2 py-1 text-xs rounded ${
                  chartMode === "daily"
                    ? "bg-gray-800 text-white"
                    : "text-gray-400 hover:text-gray-200"
                }`}
              >
                Daily
              </button>
              <button
                onClick={() => setChartMode("cumulative")}
                className={`px-2 py-1 text-xs rounded ${
                  chartMode === "cumulative"
                    ? "bg-gray-800 text-white"
                    : "text-gray-400 hover:text-gray-200"
                }`}
              >
                Cumulative
              </button>
            </div>
          </div>
        }
        span={3}
      >
        {chartData.length === 0 ? (
          <div className="h-[320px] flex items-center justify-center text-gray-600 text-sm">
            {loading ? "Loading..." : "No data in this range"}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            {chartMode === "cumulative" ? (
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="mainGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={activeMetric.color} stopOpacity={0.4} />
                    <stop offset="95%" stopColor={activeMetric.color} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={{ stroke: "#374151" }}
                  minTickGap={32}
                />
                <YAxis
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={{ stroke: "#374151" }}
                  tickFormatter={(v) => fmt(v as number)}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#0b1120",
                    border: "1px solid #374151",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                  formatter={(v) => [fmt(Number(v)), activeMetric.label]}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke={activeMetric.color}
                  fill="url(#mainGrad)"
                  strokeWidth={2}
                />
              </AreaChart>
            ) : (
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={{ stroke: "#374151" }}
                  minTickGap={24}
                />
                <YAxis
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={{ stroke: "#374151" }}
                  tickFormatter={(v) => fmt(v as number)}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#0b1120",
                    border: "1px solid #374151",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                  formatter={(v) => [fmt(Number(v)), activeMetric.label]}
                />
                <Bar dataKey="value" fill={activeMetric.color} radius={[3, 3, 0, 0]} />
              </BarChart>
            )}
          </ResponsiveContainer>
        )}
      </PanelCard>

      {/* Followers chart + Best-time heatmap */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <PanelCard title="Total followers (combined)" span={2}>
          {followerChart.length === 0 ? (
            <div className="h-[240px] flex items-center justify-center text-gray-600 text-sm">
              {loading ? "Loading..." : "No follower data yet"}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={followerChart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={{ stroke: "#374151" }}
                  minTickGap={32}
                />
                <YAxis
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={{ stroke: "#374151" }}
                  tickFormatter={(v) => fmt(v as number)}
                  domain={["auto", "auto"]}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#0b1120",
                    border: "1px solid #374151",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                  formatter={(v) => fmt(Number(v))}
                />
                <Line
                  type="monotone"
                  dataKey="total"
                  stroke="#8b5cf6"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </PanelCard>

        <PanelCard title="Best time to post (UTC)">
          <BestTimeHeatmap heatmap={heatmap} error={bestTimeError} />
        </PanelCard>
      </div>

      {/* Content decay */}
      <PanelCard title="Engagement accumulation curve" span={3}>
        {decayError ? (
          <div className="h-[180px] flex items-center justify-center text-gray-600 text-sm">
            {decayError.includes("404")
              ? "Not enough data yet for decay analysis"
              : "Couldn't load content decay (Zernio Analytics add-on required)"}
          </div>
        ) : decayChart.length === 0 ? (
          <div className="h-[180px] flex items-center justify-center text-gray-600 text-sm">
            Loading...
          </div>
        ) : (
          <>
            <p className="text-xs text-gray-500 mb-3">
              How fast posts accumulate engagement after publish — shows what
              fraction of a post's lifetime engagement is reached by each time
              window.
            </p>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={decayChart}>
                <defs>
                  <linearGradient id="decayGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis
                  dataKey="label"
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={{ stroke: "#374151" }}
                />
                <YAxis
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={{ stroke: "#374151" }}
                  tickFormatter={(v) => `${v}%`}
                  domain={[0, 100]}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#0b1120",
                    border: "1px solid #374151",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                  formatter={(v) => [`${Number(v).toFixed(1)}%`, "of lifetime"]}
                />
                <Area
                  type="monotone"
                  dataKey="pct"
                  stroke="#06b6d4"
                  fill="url(#decayGrad)"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </>
        )}
      </PanelCard>

      {/* Leaderboard */}
      <PanelCard title="Per-account performance" span={3}>
        <div className="overflow-x-auto -mx-5">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-xs uppercase tracking-wider text-gray-500">
                <th className="text-left font-medium px-5 py-2">Account</th>
                <th className="text-right font-medium py-2">Posts</th>
                <th className="text-right font-medium py-2">Views</th>
                <th className="text-right font-medium py-2">Engagement</th>
                <th className="text-right font-medium py-2">Rate</th>
                <th className="text-right font-medium py-2">Followers</th>
                <th className="text-right font-medium px-5 py-2">Δ</th>
              </tr>
            </thead>
            <tbody>
              {(data?.leaderboard ?? []).map((row) => (
                <tr
                  key={row.account_id}
                  className="border-b border-gray-800 last:border-b-0 hover:bg-gray-800/40"
                >
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-3">
                      {row.avatar_url ? (
                        <img
                          src={row.avatar_url}
                          alt=""
                          className="w-7 h-7 rounded-full bg-gray-800"
                        />
                      ) : (
                        <div className="w-7 h-7 rounded-full bg-gray-800" />
                      )}
                      <div>
                        <div className="text-white font-medium">
                          {row.display_name}
                        </div>
                        {row.username && (
                          <div className="text-xs text-gray-500">
                            @{row.username}
                          </div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="text-right tabular-nums text-gray-300">
                    {row.post_count}
                  </td>
                  <td className="text-right tabular-nums text-white">
                    {fmt(row.views)}
                  </td>
                  <td className="text-right tabular-nums text-gray-300">
                    {fmt(row.engagement)}
                  </td>
                  <td className="text-right tabular-nums text-gray-300">
                    {fmtPct(row.engagement_rate)}
                  </td>
                  <td className="text-right tabular-nums text-gray-300">
                    {fmt(row.follower_count)}
                  </td>
                  <td
                    className={`text-right px-5 tabular-nums ${
                      row.follower_delta > 0
                        ? "text-emerald-400"
                        : row.follower_delta < 0
                        ? "text-rose-400"
                        : "text-gray-500"
                    }`}
                  >
                    {fmtSigned(row.follower_delta)}
                  </td>
                </tr>
              ))}
              {(data?.leaderboard ?? []).length === 0 && (
                <tr>
                  <td
                    colSpan={7}
                    className="text-center text-gray-600 py-8 text-sm"
                  >
                    No accounts yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </PanelCard>

      {/* Top posts */}
      <PanelCard title={`Top posts (last ${range === "all" ? "all time" : days + "d"})`} span={3}>
        <div className="overflow-x-auto -mx-5">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-xs uppercase tracking-wider text-gray-500">
                <th className="text-left font-medium px-5 py-2">Account</th>
                <th className="text-left font-medium py-2">Caption</th>
                <th className="text-left font-medium py-2">Published</th>
                <th className="text-right font-medium py-2">Views</th>
                <th className="text-right font-medium py-2">Likes</th>
                <th className="text-right font-medium py-2">Comments</th>
                <th className="text-right font-medium px-5 py-2">Rate</th>
              </tr>
            </thead>
            <tbody>
              {(data?.top_posts ?? []).map((p) => (
                <tr
                  key={p.post_id}
                  className="border-b border-gray-800 last:border-b-0 hover:bg-gray-800/40"
                >
                  <td className="px-5 py-3 text-gray-300 whitespace-nowrap">
                    {p.account_name}
                    {p.status === "deleted" && (
                      <span className="ml-2 text-[10px] uppercase text-gray-600">
                        deleted
                      </span>
                    )}
                  </td>
                  <td className="py-3 text-gray-200 max-w-[420px] truncate">
                    {p.caption || (
                      <span className="text-gray-600 italic">—</span>
                    )}
                  </td>
                  <td className="py-3 text-gray-500 whitespace-nowrap">
                    {p.published_at
                      ? new Date(p.published_at).toLocaleDateString("en-US", {
                          month: "short",
                          day: "numeric",
                        })
                      : "—"}
                  </td>
                  <td className="text-right tabular-nums text-white">
                    {fmt(p.views)}
                  </td>
                  <td className="text-right tabular-nums text-gray-300">
                    {fmt(p.likes)}
                  </td>
                  <td className="text-right tabular-nums text-gray-300">
                    {fmt(p.comments)}
                  </td>
                  <td className="text-right px-5 tabular-nums text-gray-300">
                    {fmtPct(p.engagement_rate)}
                  </td>
                </tr>
              ))}
              {(data?.top_posts ?? []).length === 0 && (
                <tr>
                  <td
                    colSpan={7}
                    className="text-center text-gray-600 py-8 text-sm"
                  >
                    No posts in this window
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </PanelCard>
    </div>
  );
}

// ---------- Best-time heatmap ----------

interface HeatmapCell {
  day: number; // 0 = Sun
  hour: number; // 0..23
  value: number;
}

function parseBestTime(resp: BestTimeResponse | null): HeatmapCell[] {
  if (!resp) return [];
  // Zernio response shape varies; defensively pull both casings/locations
  const slots: HeatmapCell[] = [];
  const candidates =
    (resp.bestTimes as unknown as Array<Record<string, unknown>>) ||
    (resp.best_times as unknown as Array<Record<string, unknown>>) ||
    (resp.slots as unknown as Array<Record<string, unknown>>) ||
    (resp.data as unknown as Array<Record<string, unknown>>) ||
    [];
  for (const c of candidates) {
    const day = Number(
      (c.dayOfWeek ?? c.day_of_week ?? c.day ?? c.dow) as number
    );
    const hour = Number((c.hour ?? c.hourOfDay ?? c.hour_of_day) as number);
    const value = Number(
      (c.avg_engagement ??
        c.avgEngagement ??
        c.engagement ??
        c.engagementRate ??
        c.score ??
        c.value ??
        0) as number
    );
    if (Number.isFinite(day) && Number.isFinite(hour)) {
      slots.push({ day, hour, value });
    }
  }
  return slots;
}

function BestTimeHeatmap({
  heatmap,
  error,
}: {
  heatmap: HeatmapCell[];
  error: string | null;
}) {
  if (error) {
    return (
      <div className="h-[240px] flex items-center justify-center text-center text-gray-600 text-sm px-4">
        {error.includes("404")
          ? "Not enough data yet — best-time needs more posts"
          : "Couldn't load best-time (Zernio Analytics add-on required)"}
      </div>
    );
  }
  if (heatmap.length === 0) {
    return (
      <div className="h-[240px] flex items-center justify-center text-gray-600 text-sm">
        Loading...
      </div>
    );
  }
  const max = heatmap.reduce((m, c) => (c.value > m ? c.value : m), 0) || 1;
  const grid = Array.from({ length: 7 }, () =>
    Array.from({ length: 24 }, () => 0)
  );
  for (const c of heatmap) {
    if (c.day >= 0 && c.day < 7 && c.hour >= 0 && c.hour < 24) {
      grid[c.day][c.hour] = c.value;
    }
  }
  const days = ["S", "M", "T", "W", "T", "F", "S"];

  return (
    <div className="overflow-x-auto">
      <div className="inline-grid gap-[2px]" style={{ gridTemplateColumns: "auto repeat(24, minmax(10px, 1fr))" }}>
        <div />
        {Array.from({ length: 24 }, (_, h) => (
          <div
            key={h}
            className="text-[9px] text-gray-600 text-center"
          >
            {h % 6 === 0 ? h : ""}
          </div>
        ))}
        {grid.map((row, d) => (
          <FragmentRow key={d} day={days[d]} row={row} max={max} />
        ))}
      </div>
      <p className="text-[10px] text-gray-600 mt-2">
        Higher engagement = brighter. Hours in UTC.
      </p>
    </div>
  );
}

function FragmentRow({
  day,
  row,
  max,
}: {
  day: string;
  row: number[];
  max: number;
}) {
  return (
    <>
      <div className="text-[10px] text-gray-500 pr-1 self-center">{day}</div>
      {row.map((v, h) => {
        const intensity = max > 0 ? v / max : 0;
        return (
          <div
            key={h}
            title={`${day} ${h}:00 — ${v.toFixed(2)}`}
            className="aspect-square rounded-sm"
            style={{
              backgroundColor:
                v > 0
                  ? `rgba(16, 185, 129, ${0.15 + intensity * 0.85})`
                  : "rgba(31, 41, 55, 0.7)",
              minHeight: 14,
            }}
          />
        );
      })}
    </>
  );
}

// ---------- Content decay ----------

function parseDecay(resp: ContentDecayResponse | null): { label: string; pct: number }[] {
  if (!resp) return [];
  const buckets =
    (resp.buckets as unknown as Array<Record<string, unknown>>) ||
    (resp.timeline as unknown as Array<Record<string, unknown>>) ||
    (resp.data as unknown as Array<Record<string, unknown>>) ||
    [];
  type Parsed = { order: number; label: string; pct: number };
  const parsed: Parsed[] = [];
  buckets.forEach((b, i) => {
    const order = Number(
      (b.bucket_order ?? b.order ?? b.bucketOrder ?? i) as number
    );
    let label: string;
    if (typeof b.bucket_label === "string" && b.bucket_label) {
      label = b.bucket_label;
    } else if (typeof b.label === "string" && b.label) {
      label = b.label;
    } else {
      const hours = Number(
        (b.hours ?? b.hour ?? b.timeWindow ?? b.window ?? 0) as number
      );
      label =
        hours < 24
          ? `${hours}h`
          : hours < 168
          ? `${Math.round(hours / 24)}d`
          : `${Math.round(hours / 168)}w`;
    }
    const pctRaw = Number(
      (b.avg_pct_of_final ??
        b.avgPctOfFinal ??
        b.pctOfTotal ??
        b.pct ??
        b.percentage ??
        b.percent ??
        0) as number
    );
    if (!Number.isFinite(pctRaw)) return;
    const pct = pctRaw <= 1 ? pctRaw * 100 : pctRaw;
    parsed.push({ order, label, pct });
  });
  parsed.sort((a, b) => a.order - b.order);
  return parsed.map(({ label, pct }) => ({ label, pct }));
}
