import { useEffect, useState } from "react";
import {
  api,
  type Account,
  type AccountMetricsSummary,
} from "@/lib/api";
import AccountCard from "@/components/AccountCard";
import MetricCard from "@/components/MetricCard";
import EmptyState from "@/components/EmptyState";
import { Eye, Heart, TrendingUp, Users, Plus, Wifi } from "lucide-react";

export default function Dashboard() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [summaries, setSummaries] = useState<AccountMetricsSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [accountData, summaryData] = await Promise.all([
          api.getAccounts(),
          api.getAccountsSummary(),
        ]);
        setAccounts(accountData.accounts);
        setSummaries(summaryData);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function handleSync() {
    try {
      const data = await api.syncAccounts();
      setAccounts(data.accounts);
      const summaryData = await api.getAccountsSummary();
      setSummaries(summaryData);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to sync accounts");
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        <div className="animate-pulse">Loading dashboard...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-400/10 border border-red-400/20 rounded-xl p-4 text-red-400">
        {error}
      </div>
    );
  }

  const summaryMap = new Map(summaries.map((s) => [s.account_id, s]));

  // Aggregate totals
  const totalViews = summaries.reduce((s, a) => s + a.total_views, 0);
  const totalLikes = summaries.reduce((s, a) => s + a.total_likes, 0);
  const totalFollowers = summaries.reduce(
    (s, a) => s + (a.follower_count ?? 0),
    0
  );
  const avgEngagement =
    summaries.length > 0
      ? summaries.reduce((s, a) => s + a.avg_engagement_rate, 0) /
        summaries.length
      : 0;
  const followerGrowth = summaries.reduce(
    (s, a) => s + (a.follower_growth_7d ?? 0),
    0
  );

  if (accounts.length === 0) {
    return (
      <EmptyState
        icon={<Wifi size={48} />}
        title="No accounts connected"
        description="Connect your TikTok accounts through Zernio to start tracking analytics, running experiments, and getting AI-powered insights."
        action={
          <button
            onClick={handleSync}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
          >
            <Plus size={16} />
            Sync from Zernio
          </button>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {accounts.length} of 5 accounts connected
          </p>
        </div>
        {accounts.length < 5 && (
          <button
            onClick={handleSync}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            <Plus size={16} />
            Sync Accounts
          </button>
        )}
      </div>

      {/* Aggregate Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Total Views"
          value={totalViews}
          icon={<Eye size={18} />}
        />
        <MetricCard
          label="Total Likes"
          value={totalLikes}
          icon={<Heart size={18} />}
        />
        <MetricCard
          label="Avg Engagement"
          value={`${avgEngagement.toFixed(1)}%`}
          icon={<TrendingUp size={18} />}
        />
        <MetricCard
          label="Total Followers"
          value={totalFollowers}
          change={followerGrowth}
          changeLabel="7d"
          icon={<Users size={18} />}
        />
      </div>

      {/* Account Cards */}
      <div>
        <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">
          Accounts
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {accounts.map((account) => (
            <AccountCard
              key={account.id}
              account={account}
              summary={summaryMap.get(account.id)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
