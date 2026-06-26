import { Link } from "react-router-dom";
import type { Account, AccountMetricsSummary } from "@/lib/api";
import {
  Eye,
  Heart,
  Users,
  TrendingUp,
  TrendingDown,
  AlertCircle,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";

interface AccountCardProps {
  account: Account;
  summary?: AccountMetricsSummary;
}

function HealthBadge({ status }: { status: string }) {
  switch (status) {
    case "healthy":
      return (
        <span className="flex items-center gap-1 text-xs text-emerald-400 bg-emerald-400/10 px-2 py-0.5 rounded-full">
          <CheckCircle2 size={12} />
          Healthy
        </span>
      );
    case "warning":
      return (
        <span className="flex items-center gap-1 text-xs text-yellow-400 bg-yellow-400/10 px-2 py-0.5 rounded-full">
          <AlertTriangle size={12} />
          Warning
        </span>
      );
    default:
      return (
        <span className="flex items-center gap-1 text-xs text-red-400 bg-red-400/10 px-2 py-0.5 rounded-full">
          <AlertCircle size={12} />
          Error
        </span>
      );
  }
}

export default function AccountCard({ account, summary }: AccountCardProps) {
  return (
    <Link
      to={`/analytics?account=${account.id}`}
      className="block bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-gray-700 transition-colors"
    >
      <div className="flex items-center gap-3 mb-4">
        {account.avatar_url ? (
          <img
            src={account.avatar_url}
            alt=""
            className="w-10 h-10 rounded-full object-cover"
          />
        ) : (
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-600 to-pink-500 flex items-center justify-center text-sm font-bold text-white">
            {account.display_name[0]}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="font-medium text-white truncate">
            {account.display_name}
          </div>
          {account.username && (
            <div className="text-xs text-gray-500">@{account.username}</div>
          )}
        </div>
        <HealthBadge status={account.health_status} />
      </div>

      {summary ? (
        <div className="grid grid-cols-2 gap-x-4 gap-y-3">
          <Stat icon={<Eye size={14} />} label="Views" value={fmt(summary.total_views)} />
          <Stat icon={<Heart size={14} />} label="Likes" value={fmt(summary.total_likes)} />
          <Stat
            icon={<TrendingUp size={14} />}
            label="Engagement"
            value={`${summary.avg_engagement_rate.toFixed(1)}%`}
          />
          <Stat
            icon={<Users size={14} />}
            label="Followers"
            value={summary.follower_count != null ? fmt(summary.follower_count) : "—"}
            change={summary.follower_growth_7d}
          />
        </div>
      ) : (
        <p className="text-sm text-gray-600">Syncing data...</p>
      )}

      {account.niche && (
        <div className="mt-3 pt-3 border-t border-gray-800">
          <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
            {account.niche}
          </span>
        </div>
      )}
    </Link>
  );
}

function Stat({
  icon,
  label,
  value,
  change,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  change?: number | null;
}) {
  return (
    <div className="flex items-start gap-2">
      <span className="text-gray-600 mt-0.5">{icon}</span>
      <div>
        <div className="text-xs text-gray-500">{label}</div>
        <div className="text-sm font-medium text-white flex items-center gap-1">
          {value}
          {change != null && change !== 0 && (
            <span
              className={`text-xs ${change > 0 ? "text-emerald-400" : "text-red-400"}`}
            >
              {change > 0 ? (
                <TrendingUp size={10} className="inline" />
              ) : (
                <TrendingDown size={10} className="inline" />
              )}{" "}
              {change > 0 ? "+" : ""}
              {change.toLocaleString()}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}
