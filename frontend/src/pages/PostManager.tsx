import { useEffect, useState, useRef } from "react";
import {
  api,
  type Account,
  type Post,
  type PostStatusType,
} from "@/lib/api";
import EmptyState from "@/components/EmptyState";
import {
  FileVideo,
  Plus,
  Upload,
  Clock,
  Send,
  RotateCcw,
  Trash2,
  CheckCircle2,
  AlertCircle,
  X,
  CalendarDays,
} from "lucide-react";

const STATUS_TABS: { value: PostStatusType | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "draft", label: "Drafts" },
  { value: "ready", label: "Ready" },
  { value: "scheduled", label: "Scheduled" },
  { value: "published", label: "Published" },
  { value: "failed", label: "Failed" },
  { value: "deleted", label: "Deleted" },
];

function statusBadge(status: PostStatusType) {
  const map: Record<PostStatusType, { bg: string; text: string }> = {
    draft: { bg: "bg-gray-700", text: "text-gray-300" },
    producing: { bg: "bg-blue-400/10", text: "text-blue-400" },
    ready: { bg: "bg-yellow-400/10", text: "text-yellow-400" },
    scheduled: { bg: "bg-purple-400/10", text: "text-purple-400" },
    published: { bg: "bg-emerald-400/10", text: "text-emerald-400" },
    failed: { bg: "bg-red-400/10", text: "text-red-400" },
    deleted: { bg: "bg-red-900/30", text: "text-red-300" },
  };
  const s = map[status] || map.draft;
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${s.bg} ${s.text}`}>
      {status}
    </span>
  );
}

export default function PostManager() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<PostStatusType | "all">("all");
  const [showCreate, setShowCreate] = useState(false);
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  async function loadPosts() {
    setLoading(true);
    try {
      const params: { status?: PostStatusType } = {};
      if (tab !== "all") params.status = tab;
      const data = await api.getPosts(params);
      setPosts(data.posts);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    api.getAccounts().then((d) => setAccounts(d.accounts));
  }, []);

  useEffect(() => {
    loadPosts();
  }, [tab]);

  async function handleAction(postId: number, action: () => Promise<unknown>) {
    setActionLoading(postId);
    try {
      await action();
      await loadPosts();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Action failed");
    } finally {
      setActionLoading(null);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Posts</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Create, schedule, and manage your TikTok posts
          </p>
        </div>
        {accounts.length > 0 && (
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            <Plus size={16} />
            New Post
          </button>
        )}
      </div>

      {/* Status Tabs */}
      <div className="flex gap-1 bg-gray-900 p-1 rounded-lg w-fit">
        {STATUS_TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => setTab(t.value)}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              tab === t.value
                ? "bg-gray-800 text-white"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Post List */}
      {loading ? (
        <div className="text-gray-500 text-center py-12 animate-pulse">Loading...</div>
      ) : posts.length === 0 ? (
        <EmptyState
          icon={<FileVideo size={48} />}
          title={tab === "all" ? "No posts yet" : `No ${tab} posts`}
          description="Create your first post to get started."
          action={
            accounts.length > 0 ? (
              <button
                onClick={() => setShowCreate(true)}
                className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              >
                <Plus size={16} />
                New Post
              </button>
            ) : undefined
          }
        />
      ) : (
        <div className="space-y-2">
          {posts.map((post) => {
            const account = accounts.find((a) => a.id === post.account_id);
            const isActing = actionLoading === post.id;

            return (
              <div
                key={post.id}
                className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex items-start gap-4 hover:border-gray-700 transition-colors"
              >
                {/* Video thumbnail placeholder */}
                <div className="w-16 h-16 rounded-lg bg-gray-800 flex items-center justify-center shrink-0">
                  {post.media_path ? (
                    <FileVideo size={20} className="text-gray-500" />
                  ) : (
                    <Upload size={20} className="text-gray-600" />
                  )}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    {statusBadge(post.status)}
                    {post.production_id && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400">
                        Produced
                      </span>
                    )}
                    {account && (
                      <span className="text-xs text-gray-500">
                        {account.display_name}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-white truncate">
                    {post.caption || "No caption"}
                  </p>
                  <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                    {post.scheduled_at && (
                      <span className="flex items-center gap-1">
                        <CalendarDays size={12} />
                        {new Date(post.scheduled_at).toLocaleString("en-US", {
                          month: "short",
                          day: "numeric",
                          hour: "numeric",
                          minute: "2-digit",
                        })}
                      </span>
                    )}
                    {post.failure_reason && (
                      <span className="flex items-center gap-1 text-red-400">
                        <AlertCircle size={12} />
                        {post.failure_reason}
                      </span>
                    )}
                    {post.published_at && (
                      <span className="flex items-center gap-1 text-emerald-400">
                        <CheckCircle2 size={12} />
                        Published{" "}
                        {new Date(post.published_at).toLocaleDateString("en-US", {
                          month: "short",
                          day: "numeric",
                        })}
                      </span>
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1.5 shrink-0">
                  {post.status === "draft" && (
                    <button
                      disabled={isActing}
                      onClick={() =>
                        handleAction(post.id, () => api.markReady(post.id))
                      }
                      className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-yellow-400 transition-colors"
                      title="Mark Ready"
                    >
                      <CheckCircle2 size={16} />
                    </button>
                  )}
                  {post.status === "ready" && (
                    <>
                      <button
                        disabled={isActing}
                        onClick={() => {
                          const time = prompt(
                            "Schedule for (ISO datetime):",
                            new Date(Date.now() + 3600000).toISOString().slice(0, 16)
                          );
                          if (time)
                            handleAction(post.id, () =>
                              api.schedulePost(post.id, new Date(time).toISOString())
                            );
                        }}
                        className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-purple-400 transition-colors"
                        title="Schedule"
                      >
                        <Clock size={16} />
                      </button>
                      <button
                        disabled={isActing}
                        onClick={() =>
                          handleAction(post.id, () => api.publishPost(post.id))
                        }
                        className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-emerald-400 transition-colors"
                        title="Publish Now"
                      >
                        <Send size={16} />
                      </button>
                    </>
                  )}
                  {post.status === "scheduled" && (
                    <button
                      disabled={isActing}
                      onClick={() =>
                        handleAction(post.id, () => api.publishPost(post.id))
                      }
                      className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-emerald-400 transition-colors"
                      title="Publish Now"
                    >
                      <Send size={16} />
                    </button>
                  )}
                  {post.status === "failed" && (
                    <button
                      disabled={isActing}
                      onClick={() =>
                        handleAction(post.id, () => api.retryPost(post.id))
                      }
                      className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-blue-400 transition-colors"
                      title="Retry"
                    >
                      <RotateCcw size={16} />
                    </button>
                  )}
                  {(post.status === "draft" || post.status === "failed") && (
                    <button
                      disabled={isActing}
                      onClick={() => {
                        if (confirm("Delete this post?"))
                          handleAction(post.id, () => api.deletePost(post.id));
                      }}
                      className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-red-400 transition-colors"
                      title="Delete"
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create Post Modal */}
      {showCreate && (
        <CreatePostModal
          accounts={accounts}
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            loadPosts();
          }}
        />
      )}
    </div>
  );
}

// --- Create Post Modal (Multi-Account) ---

function CreatePostModal({
  accounts,
  onClose,
  onCreated,
}: {
  accounts: Account[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [selectedAccounts, setSelectedAccounts] = useState<Set<number>>(
    new Set(accounts.map((a) => a.id))
  );
  const [captions, setCaptions] = useState<Record<number, string>>(
    Object.fromEntries(accounts.map((a) => [a.id, ""]))
  );
  const [mediaUrl, setMediaUrl] = useState("");
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [scheduleAt, setScheduleAt] = useState("");
  const [publishNow, setPublishNow] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function toggleAccount(id: number) {
    setSelectedAccounts((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function applyToAll(caption: string) {
    setCaptions((prev) => {
      const next = { ...prev };
      for (const id of selectedAccounts) next[id] = caption;
      return next;
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (selectedAccounts.size === 0) return;
    setSubmitting(true);
    setError(null);

    try {
      // Upload file first if selected
      let finalMediaUrl = mediaUrl;
      if (videoFile && !mediaUrl) {
        setUploading(true);
        finalMediaUrl = await api.uploadToZernio(videoFile);
        setUploading(false);
      }

      const accountEntries = [...selectedAccounts].map((id) => ({
        account_id: id,
        caption: captions[id] || "",
      }));

      if (selectedAccounts.size === 1 && !publishNow && !scheduleAt) {
        // Single account draft — use regular create
        const entry = accountEntries[0];
        await api.createPost({
          account_id: entry.account_id,
          caption: entry.caption || undefined,
        });
      } else {
        // Multi-account or publish/schedule — use multi endpoint
        await api.createMultiPost({
          accounts: accountEntries,
          media_url: finalMediaUrl || undefined,
          scheduled_at: scheduleAt ? new Date(scheduleAt).toISOString() : undefined,
          publish_now: publishNow,
        });
      }
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create post");
      setUploading(false);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl w-full max-w-2xl mx-4 overflow-hidden max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 shrink-0">
          <h2 className="text-lg font-semibold text-white">New Post</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4 overflow-auto">
          {/* Account Selection */}
          <div>
            <label className="block text-sm text-gray-400 mb-2">
              Accounts ({selectedAccounts.size} selected)
            </label>
            <div className="space-y-1.5">
              {accounts.map((a) => (
                <label
                  key={a.id}
                  className={`flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors ${
                    selectedAccounts.has(a.id)
                      ? "bg-blue-600/10 border border-blue-500/30"
                      : "bg-gray-800 border border-transparent hover:border-gray-700"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selectedAccounts.has(a.id)}
                    onChange={() => toggleAccount(a.id)}
                    className="rounded bg-gray-700 border-gray-600 text-blue-500 focus:ring-blue-500"
                  />
                  {a.avatar_url ? (
                    <img src={a.avatar_url} alt="" className="w-7 h-7 rounded-full" />
                  ) : (
                    <div className="w-7 h-7 rounded-full bg-gray-700 flex items-center justify-center text-xs font-bold">
                      {a.display_name[0]}
                    </div>
                  )}
                  <span className="text-sm text-white">{a.display_name}</span>
                  <span className="text-xs text-gray-500">@{a.username}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Per-Account Captions */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm text-gray-400">Captions</label>
              {selectedAccounts.size > 1 && (
                <button
                  type="button"
                  onClick={() => {
                    const first = [...selectedAccounts][0];
                    if (first && captions[first]) applyToAll(captions[first]);
                  }}
                  className="text-xs text-blue-400 hover:text-blue-300"
                >
                  Copy first to all
                </button>
              )}
            </div>
            <div className="space-y-3">
              {accounts
                .filter((a) => selectedAccounts.has(a.id))
                .map((a) => (
                  <div key={a.id}>
                    <div className="text-xs text-gray-500 mb-1">
                      @{a.username}
                    </div>
                    <textarea
                      value={captions[a.id] || ""}
                      onChange={(e) =>
                        setCaptions((prev) => ({ ...prev, [a.id]: e.target.value }))
                      }
                      rows={2}
                      placeholder={`Caption for ${a.display_name}...`}
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 resize-none focus:outline-none focus:border-blue-500"
                    />
                    <div className="text-xs text-gray-600 text-right">
                      {(captions[a.id] || "").length}/2200
                    </div>
                  </div>
                ))}
            </div>
          </div>

          {/* Video Upload */}
          <div>
            <label className="block text-sm text-gray-400 mb-1.5">Video</label>
            <input
              ref={fileRef}
              type="file"
              accept="video/mp4,video/mov,video/webm,video/*"
              onChange={(e) => {
                setVideoFile(e.target.files?.[0] ?? null);
                if (e.target.files?.[0]) setMediaUrl("");
              }}
              className="hidden"
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={!!mediaUrl}
              className="w-full bg-gray-800 border border-dashed border-gray-700 rounded-lg px-3 py-4 text-sm text-gray-400 hover:border-gray-500 hover:text-gray-300 transition-colors flex items-center justify-center gap-2 disabled:opacity-40"
            >
              <Upload size={16} />
              {videoFile ? videoFile.name : "Choose video file"}
            </button>

            <div className="flex items-center gap-2 my-2">
              <div className="flex-1 border-t border-gray-800" />
              <span className="text-xs text-gray-600">or paste URL</span>
              <div className="flex-1 border-t border-gray-800" />
            </div>

            <input
              value={mediaUrl}
              onChange={(e) => {
                setMediaUrl(e.target.value);
                if (e.target.value) setVideoFile(null);
              }}
              placeholder="https://cdn.example.com/video.mp4"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Schedule / Publish */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm text-gray-400 mb-1.5">
                Schedule (optional)
              </label>
              <input
                type="datetime-local"
                value={scheduleAt}
                onChange={(e) => {
                  setScheduleAt(e.target.value);
                  if (e.target.value) setPublishNow(false);
                }}
                disabled={publishNow}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 disabled:opacity-40"
              />
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 px-3 py-2.5 bg-gray-800 rounded-lg cursor-pointer hover:bg-gray-750 transition-colors">
                <input
                  type="checkbox"
                  checked={publishNow}
                  onChange={(e) => {
                    setPublishNow(e.target.checked);
                    if (e.target.checked) setScheduleAt("");
                  }}
                  className="rounded bg-gray-700 border-gray-600 text-blue-500 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-300">Publish now</span>
              </label>
            </div>
          </div>

          {error && (
            <div className="text-sm text-red-400 bg-red-400/10 px-3 py-2 rounded-lg">
              {error}
            </div>
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
              disabled={submitting || selectedAccounts.size === 0}
              className="flex-1 px-4 py-2.5 rounded-lg text-sm font-medium bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {uploading
                ? "Uploading video..."
                : submitting
                ? "Posting..."
                : publishNow
                ? `Publish to ${selectedAccounts.size} account${selectedAccounts.size > 1 ? "s" : ""}`
                : scheduleAt
                ? `Schedule for ${selectedAccounts.size} account${selectedAccounts.size > 1 ? "s" : ""}`
                : `Create Draft${selectedAccounts.size > 1 ? "s" : ""}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
