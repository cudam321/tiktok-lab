const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  // 204 No Content and other empty-body successes must not call .json()
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }
  return res.json();
}

// --- Types ---

export interface Account {
  id: number;
  zernio_id: string;
  display_name: string;
  username: string | null;
  avatar_url: string | null;
  niche: string | null;
  health_status: string;
  connected_at: string;
  last_synced_at: string | null;
}

export interface AccountListResponse {
  accounts: Account[];
  count: number;
  // null means no cap (dashboard tracks unlimited accounts)
  max_accounts: number | null;
}

export interface AccountMetricsSummary {
  account_id: number;
  display_name: string;
  total_posts: number;
  total_views: number;
  total_likes: number;
  avg_engagement_rate: number;
  follower_count: number | null;
  follower_growth_7d: number | null;
}

export interface PostMetric {
  post_id: number;
  caption: string | null;
  published_at: string | null;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  engagement_rate: number;
}

export interface FollowerTrendPoint {
  date: string;
  count: number;
  growth_abs: number;
  growth_pct: number;
}

export interface FollowerTrendResponse {
  account_id: number;
  display_name: string;
  data: FollowerTrendPoint[];
}

// Combined cross-account analytics
export interface CombinedKpiAlltime {
  views: number;
  likes: number;
  comments: number;
  shares: number;
  engagement: number;
  engagement_rate: number;
}

export interface CombinedFollowerKpis {
  current: number;
  delta: number;
  gained: number;
  lost: number;
}

export interface CombinedKpis {
  views: number;
  likes: number;
  comments: number;
  shares: number;
  engagement: number;
  engagement_rate: number;
  posts: number;
  alltime: CombinedKpiAlltime;
  followers: CombinedFollowerKpis;
}

export interface CombinedTimeseriesPoint {
  date: string;
  views_cumulative: number;
  likes_cumulative: number;
  comments_cumulative: number;
  shares_cumulative: number;
  engagement_cumulative: number;
  views_daily: number;
  likes_daily: number;
  comments_daily: number;
  shares_daily: number;
  engagement_daily: number;
}

export interface CombinedFollowerPoint {
  date: string;
  total: number;
  delta: number;
}

export interface LeaderboardRow {
  account_id: number;
  display_name: string;
  username: string | null;
  avatar_url: string | null;
  post_count: number;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  engagement: number;
  engagement_rate: number;
  views_alltime: number;
  follower_count: number | null;
  follower_delta: number;
}

export interface TopPost {
  post_id: number;
  account_id: number;
  account_name: string;
  caption: string | null;
  published_at: string | null;
  status: string;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  engagement: number;
  engagement_rate: number;
  views_total: number;
  engagement_rate_total: number;
}

export interface CombinedAnalytics {
  window: {
    start: string;
    end: string;
    days: number | null;
    earliest_data: string | null;
  };
  kpis: CombinedKpis;
  timeseries: CombinedTimeseriesPoint[];
  followers_timeseries: CombinedFollowerPoint[];
  leaderboard: LeaderboardRow[];
  top_posts: TopPost[];
}

export interface BestTimeResponse {
  bestTimes?: { dayOfWeek: number; hour: number; engagement: number }[];
  best_times?: { day_of_week: number; hour: number; engagement: number }[];
  [k: string]: unknown;
}

export interface ContentDecayResponse {
  buckets?: { hours: number; pctOfTotal: number }[];
  [k: string]: unknown;
}

export interface PostingFrequencyResponse {
  [k: string]: unknown;
}

export type PostStatusType =
  | "draft"
  | "producing"
  | "ready"
  | "scheduled"
  | "published"
  | "failed"
  | "deleted";

export interface Post {
  id: number;
  account_id: number;
  zernio_post_id: string | null;
  status: PostStatusType;
  caption: string | null;
  media_path: string | null;
  tiktok_settings: Record<string, unknown> | null;
  scheduled_at: string | null;
  published_at: string | null;
  failure_reason: string | null;
  retry_count: number;
  production_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface PostListResponse {
  posts: Post[];
  total: number;
}

export interface InsightResponse {
  id: number;
  type: "briefing" | "alert" | "suggestion" | "experiment_result";
  title: string;
  body: string;
  priority: "low" | "medium" | "high" | "critical";
  is_read: boolean;
  is_acted_on: boolean;
  account_id: number | null;
  created_at: string;
}

export type ExperimentStatusType =
  | "draft"
  | "running"
  | "paused"
  | "completed"
  | "cancelled";

export interface ExperimentResponse {
  id: number;
  name: string;
  hypothesis: string | null;
  variable: string;
  variants: string[];
  metric_target: string;
  min_sample_size: number;
  status: ExperimentStatusType;
  result_summary: string | null;
  confidence: number | null;
  account_id: number | null;
  created_at: string;
  completed_at: string | null;
}

export interface VariantStats {
  n: number;
  mean: number | null;
  median: number | null;
  std: number | null;
}

export interface ExperimentComparison {
  experiment_id: number;
  metric: string;
  variants: Record<string, VariantStats>;
  mann_whitney: {
    u_stat: number | null;
    z_score: number | null;
    p_value: number | null;
    significant: boolean;
  };
  bayesian: {
    prob_b_better: number | null;
    mean_diff: number | null;
    ci_lower: number | null;
    ci_upper: number | null;
    preliminary: boolean;
    sample_sizes?: Record<string, number>;
  };
  conclusion: string;
}

// --- Phase 6: Production Types ---

export interface VariablePreset {
  id: number;
  name: string;
  variable_type: string;
  remotion_composition: string;
  params: Record<string, unknown>;
  pre_process: { tool: string; inputs: Record<string, unknown> }[] | null;
  preview_thumbnail: string | null;
  created_at: string;
  updated_at: string | null;
}

export type ProductionStatusType =
  | "uploaded"
  | "analyzing"
  | "ready"
  | "rendering"
  | "done"
  | "failed";

export type RenderStatusType = "pending" | "rendering" | "done" | "failed";

export interface ProductionVariant {
  id: number;
  production_id: number;
  preset_id: number | null;
  variant_label: string;
  tool_config: Record<string, unknown>;
  render_status: RenderStatusType;
  output_path: string | null;
  error_message: string | null;
  post_id: number | null;
  created_at: string;
}

export interface Production {
  id: number;
  source_video_path: string;
  analysis: Record<string, unknown> | null;
  status: ProductionStatusType;
  created_at: string;
  variants: ProductionVariant[];
}

export interface ToolInfo {
  name: string;
  tier: string;
  capability: string;
  input_schema: Record<string, unknown> | null;
  status: string;
}

export interface VariantPreviewData {
  composition: string;
  props: Record<string, unknown>;
  pre_process: { tool: string; inputs: Record<string, unknown> }[];
}

export interface VariantProgress {
  percent: number;
  phase: string;
}

export interface RenderStatusResponse {
  production_status: string;
  variants: {
    id: number;
    label: string;
    render_status: string;
    output_path: string | null;
    error: string | null;
    progress: VariantProgress | null;
  }[];
}

// --- API Calls ---

export const api = {
  // Accounts
  getAccounts: () => request<AccountListResponse>("/accounts"),
  getAccountsSummary: () => request<AccountMetricsSummary[]>("/analytics/summary"),
  syncAccounts: () => request<AccountListResponse>("/accounts/sync"),
  deleteAccount: (id: number) =>
    request<{ detail: string }>(`/accounts/${id}`, { method: "DELETE" }),
  updateAccount: (id: number, data: { niche?: string }) =>
    request<Account>(`/accounts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  // Analytics
  getPostMetrics: (accountId: number, days = 30) =>
    request<PostMetric[]>(`/analytics/posts/${accountId}?days=${days}`),
  getFollowerTrend: (accountId: number, days = 30) =>
    request<FollowerTrendResponse>(`/analytics/followers/${accountId}?days=${days}`),
  getCombinedAnalytics: (days: number) =>
    request<CombinedAnalytics>(`/analytics/combined?days=${days}`),
  getBestTimeToPost: (platform = "tiktok") =>
    request<BestTimeResponse>(`/analytics/combined/best-time?platform=${platform}`),
  getContentDecay: (platform = "tiktok") =>
    request<ContentDecayResponse>(`/analytics/combined/decay?platform=${platform}`),
  getPostingFrequency: (platform = "tiktok") =>
    request<PostingFrequencyResponse>(
      `/analytics/combined/posting-frequency?platform=${platform}`
    ),

  // Posts
  getPosts: (params?: { account_id?: number; status?: PostStatusType }) => {
    const search = new URLSearchParams();
    if (params?.account_id) search.set("account_id", String(params.account_id));
    if (params?.status) search.set("status", params.status);
    const qs = search.toString();
    return request<PostListResponse>(`/posts${qs ? `?${qs}` : ""}`);
  },
  getPost: (id: number) => request<Post>(`/posts/${id}`),
  createPost: (data: {
    account_id: number;
    caption?: string;
    tiktok_settings?: Record<string, unknown>;
    scheduled_at?: string;
  }) => request<Post>("/posts", { method: "POST", body: JSON.stringify(data) }),
  updatePost: (id: number, data: { caption?: string; scheduled_at?: string }) =>
    request<Post>(`/posts/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  getUploadUrl: (filename: string, contentType: string) =>
    request<{ uploadUrl: string; publicUrl: string }>(
      `/posts/upload-url?filename=${encodeURIComponent(filename)}&content_type=${encodeURIComponent(contentType)}`
    ),
  uploadToZernio: async (file: File): Promise<string> => {
    const contentType = file.type || "video/mp4";
    // 1. Get presigned URL from Zernio via our backend
    const { uploadUrl, publicUrl } = await api.getUploadUrl(file.name, contentType);
    // 2. PUT the file directly to the presigned URL
    const putRes = await fetch(uploadUrl, {
      method: "PUT",
      body: file,
      headers: { "Content-Type": file.type || "video/mp4" },
    });
    if (!putRes.ok) throw new Error(`Upload failed: ${putRes.status}`);
    return publicUrl;
  },
  uploadVideo: async (postId: number, file: File): Promise<Post> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/posts/${postId}/upload`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },
  markReady: (id: number) =>
    request<Post>(`/posts/${id}/ready`, { method: "POST" }),
  schedulePost: (id: number, scheduled_at: string) =>
    request<Post>(`/posts/${id}/schedule`, {
      method: "POST",
      body: JSON.stringify({ scheduled_at }),
    }),
  publishPost: (id: number) =>
    request<Post>(`/posts/${id}/publish`, { method: "POST" }),
  retryPost: (id: number) =>
    request<Post>(`/posts/${id}/retry`, { method: "POST" }),
  deletePost: (id: number) =>
    request<{ detail: string }>(`/posts/${id}`, { method: "DELETE" }),
  createMultiPost: (data: {
    accounts: { account_id: number; caption: string }[];
    media_url?: string;
    tiktok_settings?: Record<string, unknown>;
    scheduled_at?: string;
    publish_now?: boolean;
  }) =>
    request<{ zernio_post_id: string | null; status: string; accounts_count: number }>(
      "/posts/multi",
      { method: "POST", body: JSON.stringify(data) }
    ),

  // Experiments
  getExperiments: (params?: { status?: string; account_id?: number }) => {
    const search = new URLSearchParams();
    if (params?.status) search.set("status", params.status);
    if (params?.account_id) search.set("account_id", String(params.account_id));
    const qs = search.toString();
    return request<ExperimentResponse[]>(`/experiments${qs ? `?${qs}` : ""}`);
  },
  getExperiment: (id: number) => request<ExperimentResponse>(`/experiments/${id}`),
  createExperiment: (data: {
    name: string;
    variable: string;
    variants: string[];
    hypothesis?: string;
    metric_target?: string;
    min_sample_size?: number;
    account_id?: number;
  }) => request<ExperimentResponse>("/experiments", { method: "POST", body: JSON.stringify(data) }),
  startExperiment: (id: number) =>
    request<ExperimentResponse>(`/experiments/${id}/start`, { method: "POST" }),
  completeExperiment: (id: number) =>
    request<ExperimentResponse>(`/experiments/${id}/complete`, { method: "POST" }),
  deleteExperiment: (id: number) =>
    request<{ detail: string }>(`/experiments/${id}`, { method: "DELETE" }),
  assignVariant: (experimentId: number, postId: number, variantName: string) =>
    request<{ id: number; post_id: number; experiment_id: number; variant_name: string }>(
      `/experiments/${experimentId}/assign`,
      { method: "POST", body: JSON.stringify({ post_id: postId, variant_name: variantName }) }
    ),
  getVariantCounts: (id: number) =>
    request<{ experiment_id: number; counts: Record<string, number> }>(
      `/experiments/${id}/counts`
    ),
  compareExperiment: (id: number) => request<ExperimentComparison>(`/experiments/${id}/compare`),
  getExperimentVariables: () =>
    request<{ variables: string[] }>("/experiments/variables"),

  // Agent
  agentChat: (message: string) =>
    request<{ response: string }>("/agent/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
  getInsights: (params?: { type?: string; unread_only?: boolean }) => {
    const search = new URLSearchParams();
    if (params?.type) search.set("type", params.type);
    if (params?.unread_only) search.set("unread_only", "true");
    const qs = search.toString();
    return request<InsightResponse[]>(`/agent/insights${qs ? `?${qs}` : ""}`);
  },
  markInsightRead: (id: number) =>
    request<{ detail: string }>(`/agent/insights/${id}/read`, { method: "POST" }),
  triggerBriefing: () => request<InsightResponse>("/agent/briefing", { method: "POST" }),
  triggerScan: () => request<InsightResponse | { detail: string }>("/agent/scan", { method: "POST" }),

  // Health
  health: () => request<{ status: string; version: string }>("/health"),

  // Presets (Workshop)
  getPresets: () => request<VariablePreset[]>("/presets"),
  createPreset: (data: {
    name: string;
    variable_type: string;
    remotion_composition: string;
    params?: Record<string, unknown>;
    pre_process?: { tool: string; inputs: Record<string, unknown> }[];
  }) => request<VariablePreset>("/presets", { method: "POST", body: JSON.stringify(data) }),
  updatePreset: (id: number, data: {
    name?: string;
    params?: Record<string, unknown>;
    pre_process?: { tool: string; inputs: Record<string, unknown> }[];
    remotion_composition?: string;
  }) => request<VariablePreset>(`/presets/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deletePreset: (id: number) =>
    request<void>(`/presets/${id}`, { method: "DELETE" }),
  testPreset: async (presetId: number, file: File): Promise<string> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/presets/${presetId}/test`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error(`Test failed: ${res.status}`);
    return URL.createObjectURL(await res.blob());
  },
  transcribeClip: async (file: File): Promise<{ captions: { word: string; startMs: number; endMs: number }[]; text: string }> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/presets/transcribe`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error(`Transcription failed: ${res.status}`);
    return res.json();
  },
  getTools: () => request<{ tools: ToolInfo[] }>("/presets/tools/list"),

  // Productions (Pipeline)
  getProductions: () => request<Production[]>("/productions"),
  getProduction: (id: number) => request<Production>(`/productions/${id}`),
  uploadProduction: async (file: File): Promise<Production> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/productions`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return res.json();
  },
  analyzeProduction: (id: number) =>
    request<{ status: string; analysis: Record<string, unknown> }>(
      `/productions/${id}/analyze`,
      { method: "POST" }
    ),
  updateTranscript: (
    id: number,
    payload: { words?: { word: string; startMs: number; endMs: number }[]; text?: string },
  ) =>
    request<{ text: string; words: { word: string; startMs: number; endMs: number }[] }>(
      `/productions/${id}/transcript`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  addVariant: (productionId: number, data: {
    preset_id?: number;
    variant_label: string;
    tool_config: Record<string, unknown>;
  }) => request<ProductionVariant>(
    `/productions/${productionId}/variants`,
    { method: "POST", body: JSON.stringify(data) }
  ),
  deleteVariant: (productionId: number, variantId: number) =>
    request<void>(`/productions/${productionId}/variants/${variantId}`, { method: "DELETE" }),
  getVariantPreview: (productionId: number, variantId: number) =>
    request<VariantPreviewData>(`/productions/${productionId}/variants/${variantId}/preview`),
  startRender: (productionId: number) =>
    request<{ status: string; message: string }>(
      `/productions/${productionId}/render`,
      { method: "POST" }
    ),
  getRenderStatus: (productionId: number) =>
    request<RenderStatusResponse>(`/productions/${productionId}/status`),
  publishProduction: (productionId: number, accountId: number) =>
    request<{ status: string; posts: { id: number; caption: string }[] }>(
      `/productions/${productionId}/publish`,
      { method: "POST", body: JSON.stringify({ account_id: accountId }) }
    ),
};
