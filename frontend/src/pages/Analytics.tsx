import { useSearchParams } from "react-router-dom";
import CombinedAnalytics from "@/components/analytics/CombinedAnalytics";
import PerAccountAnalytics from "@/components/analytics/PerAccountAnalytics";

export default function Analytics() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") === "account" ? "account" : "combined";

  const setTab = (next: "combined" | "account") => {
    const sp = new URLSearchParams(searchParams);
    if (next === "combined") {
      sp.delete("tab");
    } else {
      sp.set("tab", "account");
    }
    setSearchParams(sp);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Analytics</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {tab === "combined"
              ? "Cross-account performance"
              : "Single-account deep dive"}
          </p>
        </div>
        <div className="inline-flex items-center bg-gray-900 border border-gray-800 rounded-lg p-1">
          <button
            onClick={() => setTab("combined")}
            className={`px-3 py-1.5 text-sm rounded-md transition ${
              tab === "combined"
                ? "bg-gray-800 text-white"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            Combined
          </button>
          <button
            onClick={() => setTab("account")}
            className={`px-3 py-1.5 text-sm rounded-md transition ${
              tab === "account"
                ? "bg-gray-800 text-white"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            Per Account
          </button>
        </div>
      </div>

      {tab === "combined" ? <CombinedAnalytics /> : <PerAccountAnalytics />}
    </div>
  );
}
