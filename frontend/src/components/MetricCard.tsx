import { type ReactNode } from "react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface MetricCardProps {
  label: string;
  value: string | number;
  change?: number | null;
  changeLabel?: string;
  icon?: ReactNode;
}

export default function MetricCard({
  label,
  value,
  change,
  changeLabel,
  icon,
}: MetricCardProps) {
  const trend =
    change == null || change === 0 ? "neutral" : change > 0 ? "up" : "down";

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-gray-400">{label}</span>
        {icon && <span className="text-gray-600">{icon}</span>}
      </div>
      <div className="text-2xl font-semibold text-white mb-1">
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
      {change != null && (
        <div
          className={`flex items-center gap-1 text-xs ${
            trend === "up"
              ? "text-emerald-400"
              : trend === "down"
              ? "text-red-400"
              : "text-gray-500"
          }`}
        >
          {trend === "up" ? (
            <TrendingUp size={14} />
          ) : trend === "down" ? (
            <TrendingDown size={14} />
          ) : (
            <Minus size={14} />
          )}
          <span>
            {change > 0 ? "+" : ""}
            {typeof change === "number" && Math.abs(change) < 1
              ? `${(change * 100).toFixed(1)}%`
              : change.toLocaleString()}
          </span>
          {changeLabel && <span className="text-gray-500">{changeLabel}</span>}
        </div>
      )}
    </div>
  );
}
