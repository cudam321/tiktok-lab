import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import {
  api,
  type Account,
  type PostMetric,
  type FollowerTrendPoint,
} from "@/lib/api";
import PostTable from "@/components/PostTable";
import { BarChart3 } from "lucide-react";
import EmptyState from "@/components/EmptyState";

export default function PerAccountAnalytics() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get("account");

  const [accounts, setAccounts] = useState<Account[]>([]);
  const [posts, setPosts] = useState<PostMetric[]>([]);
  const [followers, setFollowers] = useState<FollowerTrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  useEffect(() => {
    api.getAccounts().then((data) => {
      setAccounts(data.accounts);
      if (!selectedId && data.accounts.length > 0) {
        const sp = new URLSearchParams(searchParams);
        sp.set("account", String(data.accounts[0].id));
        setSearchParams(sp);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setLoading(true);
    Promise.all([
      api.getPostMetrics(Number(selectedId), days),
      api.getFollowerTrend(Number(selectedId), days),
    ])
      .then(([postData, followerData]) => {
        setPosts(postData);
        setFollowers(followerData.data);
      })
      .catch(() => {
        setPosts([]);
        setFollowers([]);
      })
      .finally(() => setLoading(false));
  }, [selectedId, days]);

  if (accounts.length === 0 && !loading) {
    return (
      <EmptyState
        icon={<BarChart3 size={48} />}
        title="No analytics yet"
        description="Connect an account to start seeing analytics data."
      />
    );
  }

  const engagementData = [...posts]
    .reverse()
    .map((p) => ({
      date: p.published_at
        ? new Date(p.published_at).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
          })
        : "—",
      views: p.views,
      engagement: p.engagement_rate,
    }));

  const followerData = followers.map((f) => ({
    date: new Date(f.date).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    }),
    count: f.count,
    growth: f.growth_abs,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-end gap-3">
        <select
          value={selectedId ?? ""}
          onChange={(e) => {
            const sp = new URLSearchParams(searchParams);
            sp.set("account", e.target.value);
            setSearchParams(sp);
          }}
          className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
        >
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.display_name}
            </option>
          ))}
        </select>

        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
        >
          <option value={7}>7 days</option>
          <option value={14}>14 days</option>
          <option value={30}>30 days</option>
          <option value={60}>60 days</option>
          <option value={90}>90 days</option>
        </select>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h3 className="text-sm font-medium text-gray-400 mb-4">
            Views per Post
          </h3>
          {engagementData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={engagementData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={{ stroke: "#374151" }}
                />
                <YAxis
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={{ stroke: "#374151" }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#111827",
                    border: "1px solid #374151",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                />
                <Bar dataKey="views" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[220px] flex items-center justify-center text-gray-600 text-sm">
              {loading ? "Loading..." : "No data"}
            </div>
          )}
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h3 className="text-sm font-medium text-gray-400 mb-4">
            Engagement Rate (%)
          </h3>
          {engagementData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={engagementData}>
                <defs>
                  <linearGradient id="engGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={{ stroke: "#374151" }}
                />
                <YAxis
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={{ stroke: "#374151" }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#111827",
                    border: "1px solid #374151",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="engagement"
                  stroke="#10b981"
                  fill="url(#engGrad)"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[220px] flex items-center justify-center text-gray-600 text-sm">
              {loading ? "Loading..." : "No data"}
            </div>
          )}
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 lg:col-span-2">
          <h3 className="text-sm font-medium text-gray-400 mb-4">
            Follower Trend
          </h3>
          {followerData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={followerData}>
                <defs>
                  <linearGradient id="follGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={{ stroke: "#374151" }}
                />
                <YAxis
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={{ stroke: "#374151" }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#111827",
                    border: "1px solid #374151",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="count"
                  stroke="#8b5cf6"
                  fill="url(#follGrad)"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[220px] flex items-center justify-center text-gray-600 text-sm">
              {loading ? "Loading..." : "No follower data"}
            </div>
          )}
        </div>
      </div>

      <div>
        <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">
          Post Performance
        </h2>
        <PostTable posts={posts} loading={loading} />
      </div>
    </div>
  );
}
