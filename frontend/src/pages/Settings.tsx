import { useEffect, useState } from "react";
import { api, type Account } from "@/lib/api";
import { RefreshCw, Trash2, ExternalLink } from "lucide-react";

export default function Settings() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [health, setHealth] = useState<{ status: string; version: string } | null>(null);

  useEffect(() => {
    api.getAccounts().then((d) => setAccounts(d.accounts));
    api.health().then(setHealth);
  }, []);

  async function handleSync() {
    setSyncing(true);
    try {
      const data = await api.syncAccounts();
      setAccounts(data.accounts);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  async function handleRemove(id: number) {
    if (!confirm("Remove this account from TikTok Lab? (Does not disconnect from Zernio)"))
      return;
    try {
      await api.deleteAccount(id);
      setAccounts((prev) => prev.filter((a) => a.id !== id));
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to remove");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Manage accounts and configuration
        </p>
      </div>

      {/* Accounts */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-medium text-white">Connected Accounts</h2>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex items-center gap-2 bg-gray-800 hover:bg-gray-700 px-3 py-1.5 rounded-lg text-sm text-gray-300 transition-colors disabled:opacity-50"
          >
            <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
            Sync from Zernio
          </button>
        </div>

        <p className="text-xs text-gray-500">
          Accounts are connected on{" "}
          <a
            href="https://zernio.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:underline inline-flex items-center gap-0.5"
          >
            Zernio's dashboard <ExternalLink size={10} />
          </a>
          . Use "Sync" to pull them here.
        </p>

        {accounts.length === 0 ? (
          <p className="text-sm text-gray-600 py-4 text-center">
            No accounts synced yet
          </p>
        ) : (
          <div className="space-y-2">
            {accounts.map((account) => (
              <div
                key={account.id}
                className="flex items-center gap-3 bg-gray-800 rounded-lg p-3"
              >
                {account.avatar_url ? (
                  <img
                    src={account.avatar_url}
                    alt=""
                    className="w-8 h-8 rounded-full"
                  />
                ) : (
                  <div className="w-8 h-8 rounded-full bg-gray-700 flex items-center justify-center text-xs font-bold">
                    {account.display_name[0]}
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-white truncate">
                    {account.display_name}
                  </div>
                  <div className="text-xs text-gray-500">
                    @{account.username} · {account.health_status}
                  </div>
                </div>
                <button
                  onClick={() => handleRemove(account.id)}
                  className="p-1.5 rounded hover:bg-gray-700 text-gray-500 hover:text-red-400 transition-colors"
                  title="Remove from TikTok Lab"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}

        <p className="text-xs text-gray-600">
          {accounts.length} of 5 accounts · To add more, connect them on Zernio first, then sync.
        </p>
      </div>

      {/* System Info */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
        <h2 className="font-medium text-white">System</h2>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="text-gray-500">Version</div>
          <div className="text-gray-300">{health?.version ?? "—"}</div>
          <div className="text-gray-500">Status</div>
          <div className="text-gray-300">{health?.status ?? "—"}</div>
          <div className="text-gray-500">Backend</div>
          <div className="text-gray-300">http://localhost:8000</div>
        </div>
      </div>
    </div>
  );
}
