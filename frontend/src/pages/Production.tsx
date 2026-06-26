import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import {
  Upload,
  Play,
  Loader2,
  Trash2,
  CheckCircle2,
  XCircle,
  Clock,
  Send,
  Pencil,
  Save,
  RotateCcw,
  Plus,
  Copy,
  X,
} from "lucide-react";
import type { ProductionVariant } from "../lib/api";
import {
  api,
  Production as ProductionType,
  VariablePreset,
  RenderStatusResponse,
} from "../lib/api";

interface TranscriptWord {
  word: string;
  startMs: number;
  endMs: number;
}

export default function Production() {
  const [productions, setProductions] = useState<ProductionType[]>([]);
  const [presets, setPresets] = useState<VariablePreset[]>([]);
  const [selected, setSelected] = useState<ProductionType | null>(null);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [renderStatus, setRenderStatus] = useState<RenderStatusResponse | null>(null);
  const [pollInterval, setPollInterval] = useState<ReturnType<typeof setInterval> | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadData = useCallback(async () => {
    try {
      const [prods, pres] = await Promise.all([
        api.getProductions(),
        api.getPresets(),
      ]);
      setProductions(prods);
      setPresets(pres);
    } catch (e) {
      console.error("Failed to load data:", e);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    return () => { if (pollInterval) clearInterval(pollInterval); };
  }, [pollInterval]);

  // Auto-resume polling if we land on a production that's already mid-render
  // (e.g. after a page refresh while a render is running).
  useEffect(() => {
    if (!selected) return;
    if (pollInterval) return;
    if (selected.status !== "rendering") return;
    const interval = setInterval(async () => {
      try {
        const status = await api.getRenderStatus(selected.id);
        setRenderStatus(status);
        if (status.production_status === "done" || status.production_status === "failed") {
          clearInterval(interval);
          setPollInterval(null);
          const updated = await api.getProduction(selected.id);
          setSelected(updated);
        }
      } catch { /* ignore poll errors */ }
    }, 1000);
    setPollInterval(interval);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.id, selected?.status]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const prod = await api.uploadProduction(file);
      await loadData();
      setSelected(prod);
    } catch (e) {
      console.error("Upload failed:", e);
    }
    setUploading(false);
  };

  const handleAnalyze = async () => {
    if (!selected) return;
    setAnalyzing(true);
    try {
      await api.analyzeProduction(selected.id);
      const updated = await api.getProduction(selected.id);
      setSelected(updated);
      loadData();
    } catch (e) {
      console.error("Analysis failed:", e);
    }
    setAnalyzing(false);
  };

  // Builder state for composing a new multi-variable variant.
  type BuilderItem = {
    preset_id: number;
    name: string;
    type: string;
    remotion_composition: string;
    params: Record<string, unknown>;
    pre_process: { tool: string; inputs: Record<string, unknown> }[] | null;
  };
  const [builderOpen, setBuilderOpen] = useState(false);
  const [builderItems, setBuilderItems] = useState<BuilderItem[]>([]);

  const resetBuilder = () => {
    setBuilderOpen(false);
    setBuilderItems([]);
  };

  const builderAddPreset = (presetId: number) => {
    const preset = presets.find(p => p.id === presetId);
    if (!preset) return;
    setBuilderItems(items => [
      ...items,
      {
        preset_id: preset.id,
        name: preset.name,
        type: preset.variable_type,
        remotion_composition: preset.remotion_composition,
        params: { ...(preset.params as Record<string, unknown>) },
        pre_process: preset.pre_process,
      },
    ]);
  };

  const builderUpdateItemParam = (idx: number, key: string, value: unknown) => {
    setBuilderItems(items =>
      items.map((it, i) => (i === idx ? { ...it, params: { ...it.params, [key]: value } } : it)),
    );
  };

  const builderRemoveItem = (idx: number) => {
    setBuilderItems(items => items.filter((_, i) => i !== idx));
  };

  const saveBuilderVariant = async () => {
    if (!selected || builderItems.length === 0) return;
    const label = String.fromCharCode(65 + (selected.variants?.length || 0));
    const toolConfig: Record<string, unknown> = {
      variables: builderItems.map(it => ({
        preset_id: it.preset_id,
        type: it.type,
        remotion_composition: it.remotion_composition,
        params: it.params,
        pre_process: it.pre_process || [],
      })),
    };
    try {
      await api.addVariant(selected.id, {
        // Tag with the first item's preset so the row can render something sensible,
        // but the real content is in tool_config.variables.
        preset_id: builderItems[0].preset_id,
        variant_label: label,
        tool_config: toolConfig,
      });
      const updated = await api.getProduction(selected.id);
      setSelected(updated);
      resetBuilder();
    } catch (e) {
      console.error("Failed to save variant:", e);
    }
  };

  const duplicateVariant = async (variantId: number) => {
    if (!selected) return;
    const source = selected.variants.find(v => v.id === variantId);
    if (!source) return;
    const label = String.fromCharCode(65 + (selected.variants?.length || 0));
    try {
      await api.addVariant(selected.id, {
        preset_id: source.preset_id || undefined,
        variant_label: label,
        tool_config: source.tool_config as Record<string, unknown>,
      });
      const updated = await api.getProduction(selected.id);
      setSelected(updated);
    } catch (e) {
      console.error("Failed to duplicate variant:", e);
    }
  };

  const handleDeleteVariant = async (variantId: number) => {
    if (!selected) return;
    try {
      await api.deleteVariant(selected.id, variantId);
      const updated = await api.getProduction(selected.id);
      setSelected(updated);
    } catch (e) {
      console.error("Failed to delete variant:", e);
    }
  };

  const handleRender = async () => {
    if (!selected) return;
    try {
      await api.startRender(selected.id);
      // Start polling
      const interval = setInterval(async () => {
        try {
          const status = await api.getRenderStatus(selected.id);
          setRenderStatus(status);
          if (status.production_status === "done" || status.production_status === "failed") {
            clearInterval(interval);
            setPollInterval(null);
            const updated = await api.getProduction(selected.id);
            setSelected(updated);
          }
        } catch { /* ignore poll errors */ }
      }, 1000);
      setPollInterval(interval);
    } catch (e) {
      console.error("Render failed:", e);
    }
  };

  const handlePublish = async (accountId: number) => {
    if (!selected) return;
    try {
      await api.publishProduction(selected.id, accountId);
      const updated = await api.getProduction(selected.id);
      setSelected(updated);
      loadData();
    } catch (e) {
      console.error("Publish failed:", e);
    }
  };

  const analysis = selected?.analysis as Record<string, unknown> | null;
  const transcript = analysis?.transcript as Record<string, unknown> | null;
  const isRendering = selected?.status === "rendering" || renderStatus?.production_status === "rendering";

  return (
    <div className="flex-1 p-6 space-y-6 overflow-y-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Produce</h1>
        <div className="flex gap-2">
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm text-white disabled:opacity-50"
          >
            {uploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
            Upload Source Video
          </button>
          <input ref={fileInputRef} type="file" accept="video/*" onChange={handleUpload} className="hidden" />
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6">
        {/* Left: Production List */}
        <div className="col-span-3 space-y-2">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
            Productions
          </h2>
          {productions.map(p => (
            <div
              key={p.id}
              onClick={() => { setSelected(p); setRenderStatus(null); }}
              className={`p-3 rounded-lg cursor-pointer border ${
                selected?.id === p.id
                  ? "border-blue-500 bg-gray-800"
                  : "border-gray-800 bg-gray-900 hover:bg-gray-850"
              }`}
            >
              <div className="text-sm text-white">Production #{p.id}</div>
              <div className="flex items-center gap-2 mt-1">
                <StatusBadge status={p.status} />
                <span className="text-xs text-gray-500">
                  {p.variants?.length || 0} variants
                </span>
              </div>
            </div>
          ))}
          {productions.length === 0 && (
            <div className="text-sm text-gray-500 p-3">
              Upload a video to start
            </div>
          )}
        </div>

        {/* Right: Production Detail */}
        <div className="col-span-9 space-y-6">
          {selected ? (
            <>
              {/* Source Video */}
              <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-white">Source Video</h3>
                  {selected.status === "uploaded" && (
                    <button
                      onClick={handleAnalyze}
                      disabled={analyzing}
                      className="flex items-center gap-2 px-3 py-1.5 bg-purple-600 hover:bg-purple-500 rounded text-sm text-white disabled:opacity-50"
                    >
                      {analyzing ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                      Analyze
                    </button>
                  )}
                </div>
                <video
                  src={`/api/productions/${selected.id}/source`}
                  controls
                  className="w-full max-h-64 rounded object-contain bg-black"
                />
              </div>

              {/* Analysis Results */}
              {analysis && (
                <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
                  <h3 className="text-sm font-semibold text-white mb-3">Analysis</h3>
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <span className="text-gray-400">Duration:</span>{" "}
                      <span className="text-white">
                        {Math.round((analysis.duration as number) || 0)}s
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-400">Resolution:</span>{" "}
                      <span className="text-white">
                        {(analysis.resolution as Record<string, number>)?.width}x
                        {(analysis.resolution as Record<string, number>)?.height}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-400">Transcript:</span>{" "}
                      <span className="text-white">
                        {transcript ? "Ready" : "N/A"}
                      </span>
                    </div>
                  </div>
                  {Array.isArray(transcript?.words) && (transcript.words as TranscriptWord[]).length > 0 && (
                    <TranscriptEditor
                      productionId={selected.id}
                      words={transcript.words as TranscriptWord[]}
                      onUpdated={async () => {
                        const updated = await api.getProduction(selected.id);
                        setSelected(updated);
                      }}
                    />
                  )}
                </div>
              )}

              {/* Variants */}
              {(selected.status === "ready" || selected.status === "rendering" || selected.status === "done") && (
                <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-white">Variants</h3>
                    <button
                      onClick={() => setBuilderOpen(true)}
                      disabled={builderOpen}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm text-white disabled:opacity-50"
                    >
                      <Plus size={14} /> New Variant
                    </button>
                  </div>

                  {builderOpen && (
                    <VariantBuilder
                      label={String.fromCharCode(65 + (selected.variants?.length || 0))}
                      items={builderItems}
                      presets={presets}
                      onAddPreset={builderAddPreset}
                      onUpdateParam={builderUpdateItemParam}
                      onRemove={builderRemoveItem}
                      onSave={saveBuilderVariant}
                      onCancel={resetBuilder}
                    />
                  )}

                  {(selected.variants?.length > 0) ? (
                    <div className="space-y-2">
                      {selected.variants.map(v => {
                        const rs = renderStatus?.variants?.find(rv => rv.id === v.id);
                        const status = rs?.render_status || v.render_status;
                        const progress = rs?.progress ?? null;
                        const chips = variantDisplayChips(v, presets);
                        return (
                          <div key={v.id} className="p-3 bg-gray-800 rounded-lg space-y-2">
                            <div className="flex items-center justify-between gap-3">
                              <div className="flex items-center gap-3 min-w-0 flex-1">
                                <span className="w-8 h-8 flex items-center justify-center rounded-full bg-blue-600 text-white text-sm font-bold shrink-0">
                                  {v.variant_label}
                                </span>
                                <div className="flex flex-wrap items-center gap-1.5 min-w-0">
                                  {chips.length > 0 ? (
                                    chips.map((c, i) => (
                                      <span
                                        key={i}
                                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gray-700 text-xs text-gray-200"
                                        title={c.subtitle}
                                      >
                                        <span>{c.label}</span>
                                        {c.subtitle && <span className="text-gray-500">· {c.subtitle}</span>}
                                      </span>
                                    ))
                                  ) : (
                                    <span className="text-xs text-gray-500">empty variant</span>
                                  )}
                                </div>
                              </div>
                              <div className="flex items-center gap-2 shrink-0">
                                <RenderStatusBadge status={status} />
                                {status === "pending" && (
                                  <>
                                    <button
                                      onClick={() => duplicateVariant(v.id)}
                                      className="p-1 text-gray-500 hover:text-blue-400"
                                      title="Duplicate"
                                    >
                                      <Copy size={14} />
                                    </button>
                                    <button
                                      onClick={() => handleDeleteVariant(v.id)}
                                      className="p-1 text-gray-500 hover:text-red-400"
                                      title="Delete"
                                    >
                                      <Trash2 size={14} />
                                    </button>
                                  </>
                                )}
                              </div>
                            </div>
                            {status === "rendering" && progress && (
                              <VariantProgressBar percent={progress.percent} phase={progress.phase} />
                            )}
                            {status === "failed" && rs?.error && (
                              <p className="text-xs text-red-400 pl-11">{rs.error}</p>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="text-sm text-gray-500 p-3 text-center">
                      Add presets to create variants
                    </div>
                  )}

                  {/* Render / Publish Actions */}
                  {selected.variants?.length > 0 && (
                    <div className="flex gap-2 mt-4">
                      {selected.status !== "done" && (
                        <button
                          onClick={handleRender}
                          disabled={isRendering || selected.variants.every(v => v.render_status === "done")}
                          className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-500 rounded text-sm text-white disabled:opacity-50"
                        >
                          {isRendering ? (
                            <><Loader2 size={14} className="animate-spin" /> Rendering...</>
                          ) : (
                            <><Play size={14} /> Render All</>
                          )}
                        </button>
                      )}
                      {selected.status === "done" && (
                        <button
                          onClick={() => handlePublish(1)} // TODO: account selector
                          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm text-white"
                        >
                          <Send size={14} /> Publish as Drafts
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="flex items-center justify-center h-64 text-gray-500">
              Select a production or upload a new video
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    uploaded: "bg-gray-700 text-gray-300",
    analyzing: "bg-yellow-900 text-yellow-300",
    ready: "bg-blue-900 text-blue-300",
    rendering: "bg-purple-900 text-purple-300",
    done: "bg-green-900 text-green-300",
    failed: "bg-red-900 text-red-300",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${styles[status] || styles.uploaded}`}>
      {status}
    </span>
  );
}

function VariantProgressBar({ percent, phase }: { percent: number; phase: string }) {
  const clamped = Math.max(0, Math.min(100, percent));
  return (
    <div className="pl-11 space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-gray-400 truncate">{phase}</span>
        <span className="text-gray-300 font-mono">{clamped.toFixed(1)}%</span>
      </div>
      <div className="h-1.5 bg-gray-900 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-blue-500 to-purple-500 transition-[width] duration-300 ease-out"
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}

function RenderStatusBadge({ status }: { status: string }) {
  const configs: Record<string, { icon: typeof Clock; color: string }> = {
    pending: { icon: Clock, color: "text-gray-400" },
    rendering: { icon: Loader2, color: "text-purple-400" },
    done: { icon: CheckCircle2, color: "text-green-400" },
    failed: { icon: XCircle, color: "text-red-400" },
  };
  const cfg = configs[status] || configs.pending;
  const Icon = cfg.icon;
  return (
    <span className={`flex items-center gap-1 text-xs ${cfg.color}`}>
      <Icon size={14} className={status === "rendering" ? "animate-spin" : ""} />
      {status}
    </span>
  );
}

// --- Transcript Editor ---
// Two modes for the same canonical transcript:
// 1. Words — each word is an inline input, timings preserved. Zero drift, OK for small edits.
// 2. Full text — freeform textarea, server realigns via sequence diff on save.
// Both modes PATCH /api/productions/{id}/transcript.

const PHRASE_GAP_MS = 450;

function groupIntoPhrases(words: TranscriptWord[]): TranscriptWord[][] {
  if (!words.length) return [];
  const phrases: TranscriptWord[][] = [];
  let current: TranscriptWord[] = [];
  const SENTENCE_END = /[.!?…]$/;
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    const prev = words[i - 1];
    const gap = prev ? w.startMs - prev.endMs : 0;
    const prevEnds = prev && SENTENCE_END.test(prev.word.trim());
    if (current.length && (prevEnds || gap > PHRASE_GAP_MS)) {
      phrases.push(current);
      current = [];
    }
    current.push(w);
  }
  if (current.length) phrases.push(current);
  return phrases;
}

function TranscriptEditor({
  productionId,
  words,
  onUpdated,
}: {
  productionId: number;
  words: TranscriptWord[];
  onUpdated: () => Promise<void> | void;
}) {
  const [mode, setMode] = useState<"words" | "text">("words");
  const [draftWords, setDraftWords] = useState<TranscriptWord[]>(words);
  const [draftText, setDraftText] = useState(() => words.map(w => w.word).join(" "));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset drafts when upstream words change (e.g. after reload or re-analyze).
  useEffect(() => {
    setDraftWords(words);
    setDraftText(words.map(w => w.word).join(" "));
  }, [words]);

  const phrases = useMemo(() => groupIntoPhrases(draftWords), [draftWords]);

  const wordsDirty = useMemo(
    () => draftWords.some((w, i) => w.word !== words[i]?.word),
    [draftWords, words],
  );
  const textDirty = useMemo(
    () => draftText.trim() !== words.map(w => w.word).join(" ").trim(),
    [draftText, words],
  );
  const dirty = mode === "words" ? wordsDirty : textDirty;

  const fmtTime = (ms: number) => {
    const s = ms / 1000;
    const mm = Math.floor(s / 60);
    const ss = (s % 60).toFixed(1);
    return `${mm}:${ss.padStart(4, "0")}`;
  };

  const saveWords = async () => {
    setSaving(true); setError(null);
    try {
      await api.updateTranscript(productionId, { words: draftWords });
      await onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally { setSaving(false); }
  };

  const saveText = async () => {
    setSaving(true); setError(null);
    try {
      await api.updateTranscript(productionId, { text: draftText });
      await onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally { setSaving(false); }
  };

  const reset = () => {
    setDraftWords(words);
    setDraftText(words.map(w => w.word).join(" "));
    setError(null);
  };

  return (
    <div className="mt-4 pt-4 border-t border-gray-800 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Pencil size={14} className="text-gray-400" />
          <h4 className="text-xs font-semibold text-gray-300 uppercase tracking-wide">Transcript</h4>
          <span className="text-xs text-gray-500">{words.length} words · {fmtTime(words[words.length - 1]?.endMs || 0)}</span>
        </div>
        <div className="flex items-center gap-1 bg-gray-800 rounded-lg p-0.5">
          <button
            onClick={() => setMode("words")}
            className={`px-2.5 py-1 text-xs rounded ${mode === "words" ? "bg-gray-700 text-white" : "text-gray-400 hover:text-white"}`}
          >
            Words
          </button>
          <button
            onClick={() => setMode("text")}
            className={`px-2.5 py-1 text-xs rounded ${mode === "text" ? "bg-gray-700 text-white" : "text-gray-400 hover:text-white"}`}
          >
            Full text
          </button>
        </div>
      </div>

      {mode === "words" ? (
        <div className="max-h-72 overflow-y-auto space-y-2 pr-1">
          {phrases.map((phrase, pi) => (
            <div key={pi} className="flex flex-wrap items-center gap-1.5 p-2 bg-gray-800/60 rounded">
              <span className="text-[10px] text-gray-500 font-mono mr-1 select-none">
                {fmtTime(phrase[0].startMs)}
              </span>
              {phrase.map((w) => {
                const idx = draftWords.indexOf(w);
                return (
                  <input
                    key={idx}
                    value={w.word}
                    onChange={e => {
                      const next = draftWords.slice();
                      next[idx] = { ...next[idx], word: e.target.value };
                      setDraftWords(next);
                    }}
                    title={`${fmtTime(w.startMs)} → ${fmtTime(w.endMs)}`}
                    className="bg-transparent border-b border-transparent focus:border-blue-500 hover:border-gray-600 text-sm text-white px-1 py-0 min-w-[2ch] outline-none font-medium"
                    style={{ width: `${Math.max(w.word.length, 1) + 1}ch` }}
                  />
                );
              })}
            </div>
          ))}
        </div>
      ) : (
        <>
          <textarea
            value={draftText}
            onChange={e => setDraftText(e.target.value)}
            rows={6}
            className="w-full p-3 bg-gray-800 border border-gray-700 rounded text-sm text-white font-sans leading-relaxed resize-y focus:border-blue-500 outline-none"
            placeholder="Edit the full transcript. Timings realign on save."
          />
          <p className="text-xs text-gray-500">
            On save, word timings are realigned to your edits via sequence diff. Fixes, additions, deletions all
            keep the rest of the transcript in sync.
          </p>
        </>
      )}

      {error && <p className="text-xs text-red-400">{error}</p>}

      <div className="flex items-center justify-end gap-2">
        {dirty && (
          <button
            onClick={reset}
            disabled={saving}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-xs disabled:opacity-50"
          >
            <RotateCcw size={12} /> Reset
          </button>
        )}
        <button
          onClick={mode === "words" ? saveWords : saveText}
          disabled={saving || !dirty}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
          {saving ? "Saving..." : "Save transcript"}
        </button>
      </div>
    </div>
  );
}

// --- VariantBuilder ---
// Inline builder for composing a multi-variable variant. User adds presets
// from a dropdown; each added preset becomes a chip with optional inline
// editors (e.g. text input for persistent_text). On save, the caller writes
// one variant whose tool_config contains a `variables` array.

type BuilderItem = {
  preset_id: number;
  name: string;
  type: string;
  remotion_composition: string;
  params: Record<string, unknown>;
  pre_process: { tool: string; inputs: Record<string, unknown> }[] | null;
};

function VariantBuilder({
  label,
  items,
  presets,
  onAddPreset,
  onUpdateParam,
  onRemove,
  onSave,
  onCancel,
}: {
  label: string;
  items: BuilderItem[];
  presets: VariablePreset[];
  onAddPreset: (presetId: number) => void;
  onUpdateParam: (idx: number, key: string, value: unknown) => void;
  onRemove: (idx: number) => void;
  onSave: () => void | Promise<void>;
  onCancel: () => void;
}) {
  return (
    <div className="mb-3 p-3 bg-blue-900/15 border border-blue-800/60 rounded-lg space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-7 h-7 flex items-center justify-center rounded-full bg-blue-600 text-white text-xs font-bold">
            {label}
          </span>
          <span className="text-xs text-gray-300">New variant — stack any mix of variables</span>
        </div>
        <button onClick={onCancel} className="text-xs text-gray-500 hover:text-gray-300">Cancel</button>
      </div>

      {items.length > 0 && (
        <div className="space-y-2">
          {items.map((it, i) => (
            <div key={i} className="p-2 bg-gray-800/70 rounded border border-gray-700/50 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-white">{it.name}</span>
                  <span className="text-[10px] uppercase tracking-wide text-gray-500">{it.type}</span>
                </div>
                <button
                  onClick={() => onRemove(i)}
                  className="p-1 text-gray-500 hover:text-red-400"
                  title="Remove"
                >
                  <X size={12} />
                </button>
              </div>

              {/* Per-preset override editors. Extend here as new variables need per-variant inputs. */}
              {it.type === "persistent_text" && (
                <div className="space-y-1">
                  <label className="text-[11px] text-gray-400">Text for this variant</label>
                  <textarea
                    value={(it.params.text as string) || ""}
                    onChange={e => onUpdateParam(i, "text", e.target.value)}
                    rows={2}
                    className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-xs text-white resize-y focus:border-blue-500 outline-none"
                    placeholder="e.g. Follow for more Paris trips"
                  />
                </div>
              )}
              {it.type === "text_overlay" && (
                <div className="space-y-1">
                  <label className="text-[11px] text-gray-400">Text for this variant</label>
                  <input
                    value={(it.params.text as string) || ""}
                    onChange={e => onUpdateParam(i, "text", e.target.value)}
                    className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-xs text-white focus:border-blue-500 outline-none"
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between">
        <select
          onChange={e => { if (e.target.value) onAddPreset(Number(e.target.value)); e.target.value = ""; }}
          className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-xs text-white"
          defaultValue=""
        >
          <option value="" disabled>+ Add preset</option>
          {presets.map(p => (
            <option key={p.id} value={p.id}>{p.name} ({p.variable_type})</option>
          ))}
        </select>
        <button
          onClick={onSave}
          disabled={items.length === 0}
          className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-xs text-white disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Save variant
        </button>
      </div>
    </div>
  );
}

// Describe a variant as compact chips for the summary row. Handles both
// multi-variable (tool_config.variables) and legacy single-variable shape.
function variantDisplayChips(
  v: ProductionVariant,
  presets: VariablePreset[],
): { label: string; subtitle?: string }[] {
  const tc = v.tool_config as Record<string, unknown>;
  const variables = tc?.variables as
    | { preset_id?: number; type?: string; params?: Record<string, unknown> }[]
    | undefined;
  if (Array.isArray(variables) && variables.length > 0) {
    return variables.map(it => {
      const preset = it.preset_id ? presets.find(p => p.id === it.preset_id) : undefined;
      const name = preset?.name || it.type || "variable";
      const override = typeof it.params?.text === "string" ? it.params.text : undefined;
      return {
        label: name,
        subtitle: override ? (override.length > 28 ? override.slice(0, 26) + "…" : override) : undefined,
      };
    });
  }
  // Legacy single-preset variant.
  const preset = v.preset_id ? presets.find(p => p.id === v.preset_id) : undefined;
  return [{
    label: preset?.name || `Variant ${v.variant_label}`,
    subtitle: preset?.variable_type,
  }];
}
