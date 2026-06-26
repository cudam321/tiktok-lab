import { useState, useEffect, useCallback, useRef } from "react";
import { Player } from "@remotion/player";
import { Plus, Trash2, Save, Upload, Loader2, Mic, FlaskConical } from "lucide-react";
import { api, VariablePreset } from "../lib/api";
import {
  VariableCaptions,
  VariableTextOverlay,
  VariableHook,
  VariablePreview,
  VariablePersistentText,
} from "../remotion/compositions";
import type { WordCaption } from "../remotion/CaptionOverlay";

const VARIABLE_TYPES = [
  { value: "color_grade", label: "Color Grade", composition: "VariablePreview", hasPreProcess: true },
  { value: "captions", label: "Captions", composition: "VariableCaptions", hasPreProcess: false },
  { value: "speed", label: "Speed", composition: "VariablePreview", hasPreProcess: true },
  { value: "text_overlay", label: "Text Overlay", composition: "VariableTextOverlay", hasPreProcess: false },
  { value: "hook_intro", label: "Hook Intro (full-screen card)", composition: "VariableHook", hasPreProcess: false },
  { value: "persistent_text", label: "Hook Text (persistent)", composition: "VariablePersistentText", hasPreProcess: false },
  { value: "edit_pace", label: "Edit Pace", composition: "VariablePreview", hasPreProcess: true },
];

const DEFAULT_PARAMS: Record<string, Record<string, unknown>> = {
  captions: {
    wordsPerPage: 4,
    fontSize: 52,
    highlightColor: "#22D3EE",
    color: "#FFFFFF",
    position: "bottom",
    positionX: 50,
    positionY: 88,
    fontFamily: '-apple-system, "SF Pro Display", "SF Pro Text", system-ui, sans-serif',
    fontWeight: 800,
    strokeColor: "#000000",
    strokeWidth: 6,
    showBackground: false,
    backgroundColor: "rgba(0, 0, 0, 0.65)",
    phraseGapMs: 450,
  },
  text_overlay: { text: "Your text here", fontSize: 48, fontWeight: 700, color: "#FFFFFF", backgroundColor: "rgba(0, 0, 0, 0.7)", position: "bottom", animation: "fade", inSeconds: 0 },
  persistent_text: {
    text: "Your hook text",
    positionX: 50,
    positionY: 15,
    fontSize: 72,
    fontFamily: '-apple-system, "SF Pro Display", "SF Pro Text", system-ui, sans-serif',
    fontWeight: 800,
    color: "#FFFFFF",
    strokeColor: "#000000",
    strokeWidth: 6,
    maxWidth: 85,
    showBackground: false,
    backgroundColor: "rgba(0, 0, 0, 0.7)",
    paddingX: 32,
    paddingY: 16,
  },
  hook_intro: { hookType: "question" as const, hookText: "Did you know?", hookDuration: 3, hookColor: "#FFFFFF", hookBackgroundColor: "#0F172A", hookFontSize: 64, transition: "fade" as const },
  color_grade: {},
  speed: {},
  edit_pace: {},
};

const COMPOSITIONS: Record<string, React.FC<any>> = {
  VariablePreview,
  VariableCaptions,
  VariableTextOverlay,
  VariableHook,
  VariablePersistentText,
};

export default function Workshop() {
  const [presets, setPresets] = useState<VariablePreset[]>([]);
  const [selected, setSelected] = useState<VariablePreset | null>(null);
  const [editParams, setEditParams] = useState<Record<string, unknown>>({});
  const [editName, setEditName] = useState("");
  const [testClip, setTestClip] = useState<File | null>(null);
  const [testClipUrl, setTestClipUrl] = useState("");
  const [processedUrl, setProcessedUrl] = useState("");
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newType, setNewType] = useState("captions");
  const [newName, setNewName] = useState("");
  const [captions, setCaptions] = useState<WordCaption[]>([]);
  const [transcribing, setTranscribing] = useState(false);
  const [videoDuration, setVideoDuration] = useState(30);

  const loadPresets = useCallback(async () => {
    try { setPresets(await api.getPresets()); } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { loadPresets(); }, [loadPresets]);

  const selectPreset = (preset: VariablePreset) => {
    setSelected(preset);
    setEditParams({ ...preset.params });
    setEditName(preset.name);
    setProcessedUrl("");
  };

  const handleTestClipUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (testClipUrl) URL.revokeObjectURL(testClipUrl);
    const url = URL.createObjectURL(file);
    setTestClip(file);
    setTestClipUrl(url);
    setProcessedUrl("");
    setCaptions([]);
    // Probe duration without revoking the URL the Player needs
    const video = document.createElement("video");
    video.preload = "metadata";
    video.onloadedmetadata = () => setVideoDuration(video.duration || 30);
    video.src = url;
  };

  const handleTranscribe = async () => {
    if (!testClip) return;
    setTranscribing(true);
    try {
      const result = await api.transcribeClip(testClip);
      setCaptions(result.captions);
    } catch (e) { console.error("Transcription failed:", e); }
    setTranscribing(false);
  };

  const handleTest = async () => {
    if (!selected || !testClip) return;
    setTesting(true);
    try { setProcessedUrl(await api.testPreset(selected.id, testClip)); } catch (e) { console.error(e); }
    setTesting(false);
  };

  const handleSave = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      const updated = await api.updatePreset(selected.id, { name: editName, params: editParams });
      setSelected(updated);
      loadPresets();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    const typeInfo = VARIABLE_TYPES.find(t => t.value === newType);
    if (!typeInfo) return;
    try {
      const preset = await api.createPreset({
        name: newName, variable_type: newType,
        remotion_composition: typeInfo.composition,
        params: DEFAULT_PARAMS[newType] || {},
      });
      setShowCreate(false); setNewName("");
      await loadPresets(); selectPreset(preset);
    } catch (e) { console.error(e); }
  };

  const handleDelete = async (id: number) => {
    try { await api.deletePreset(id); if (selected?.id === id) setSelected(null); loadPresets(); } catch (e) { console.error(e); }
  };

  const updateParam = (key: string, value: unknown) => {
    setEditParams(prev => ({ ...prev, [key]: value }));
  };

  const typeInfo = selected ? VARIABLE_TYPES.find(t => t.value === selected.variable_type) : null;
  const videoSrc = processedUrl || testClipUrl;

  // Build Remotion Player props
  const compositionName = typeInfo?.composition || "VariablePreview";
  const Comp = COMPOSITIONS[compositionName] || VariablePreview;
  const fps = 30;
  const durationInFrames = Math.max(Math.ceil(videoDuration * fps), fps);

  const playerProps: Record<string, unknown> = {
    videoSrc,
    ...editParams,
  };
  if (selected?.variable_type === "captions") {
    playerProps.captions = captions;
  }

  // Draggable caption position (captions variable only)
  const playerFrameRef = useRef<HTMLDivElement>(null);
  const supportsDragPosition =
    selected?.variable_type === "captions" ||
    selected?.variable_type === "persistent_text";
  const dragPosX = (editParams.positionX as number) ?? 50;
  const dragPosY = (editParams.positionY as number)
    ?? (selected?.variable_type === "persistent_text" ? 15 : 88);

  const handlePositionDragStart = (e: React.PointerEvent) => {
    const frame = playerFrameRef.current;
    if (!frame) return;
    e.preventDefault();
    const rect = frame.getBoundingClientRect();
    const startX = e.clientX;
    const startY = e.clientY;
    const startPosX = dragPosX;
    const startPosY = dragPosY;
    const clamp = (v: number) => Math.max(0, Math.min(100, v));

    const move = (ev: PointerEvent) => {
      const dxPct = ((ev.clientX - startX) / rect.width) * 100;
      const dyPct = ((ev.clientY - startY) / rect.height) * 100;
      setEditParams(prev => ({
        ...prev,
        positionX: clamp(startPosX + dxPct),
        positionY: clamp(startPosY + dyPct),
      }));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  return (
    <div className="flex h-full">
      {/* Left: Preset List */}
      <div className="w-64 border-r border-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-800 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white">Presets</h2>
          <button onClick={() => setShowCreate(!showCreate)} className="p-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white">
            <Plus size={14} />
          </button>
        </div>
        {showCreate && (
          <div className="p-3 border-b border-gray-800 space-y-2">
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Preset name"
              className="w-full px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-white" />
            <select value={newType} onChange={e => setNewType(e.target.value)}
              className="w-full px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-white">
              {VARIABLE_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
            <button onClick={handleCreate} className="w-full px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm text-white">Create</button>
          </div>
        )}
        <div className="flex-1 overflow-y-auto">
          {presets.map(p => (
            <div key={p.id} onClick={() => selectPreset(p)}
              className={`flex items-center justify-between px-4 py-3 cursor-pointer border-b border-gray-800/50 ${selected?.id === p.id ? "bg-gray-800" : "hover:bg-gray-900"}`}>
              <div>
                <div className="text-sm text-white">{p.name}</div>
                <div className="text-xs text-gray-500">{p.variable_type}</div>
              </div>
              <button onClick={e => { e.stopPropagation(); handleDelete(p.id); }} className="p-1 text-gray-600 hover:text-red-400">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          {presets.length === 0 && <div className="p-4 text-sm text-gray-500 text-center">No presets yet</div>}
        </div>
      </div>

      {/* Center: Parameter Editor */}
      <div className="flex-1 flex flex-col min-w-0">
        {selected ? (
          <>
            <div className="p-4 border-b border-gray-800 flex items-center gap-3">
              <input value={editName} onChange={e => setEditName(e.target.value)}
                className="flex-1 px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-white text-sm" />
              <span className="px-2 py-0.5 rounded bg-gray-700 text-xs text-gray-300">{selected.variable_type}</span>
              <button onClick={handleSave} disabled={saving}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm text-white disabled:opacity-50">
                <Save size={14} /> {saving ? "Saving..." : "Save"}
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {/* Test Clip Upload */}
              <div className="space-y-2">
                <label className="text-xs font-medium text-gray-400 uppercase tracking-wide">Test Clip</label>
                <label className="flex items-center gap-2 px-3 py-2 bg-gray-800 border border-gray-700 rounded cursor-pointer hover:bg-gray-750">
                  <Upload size={14} className="text-gray-400" />
                  <span className="text-sm text-gray-300">{testClip ? testClip.name : "Upload video"}</span>
                  <input type="file" accept="video/*" onChange={handleTestClipUpload} className="hidden" />
                </label>
              </div>

              {/* Transcribe (captions only) */}
              {selected.variable_type === "captions" && testClip && (
                <div className="space-y-2">
                  <button onClick={handleTranscribe} disabled={transcribing}
                    className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded text-sm text-white disabled:opacity-50">
                    {transcribing ? <><Loader2 size={14} className="animate-spin" /> Transcribing...</> : <><Mic size={14} /> Transcribe</>}
                  </button>
                  {captions.length > 0 && <p className="text-xs text-green-400">{captions.length} words detected</p>}
                </div>
              )}

              {/* Param controls */}
              {selected.variable_type === "captions" && <CaptionParams params={editParams} onChange={updateParam} />}
              {selected.variable_type === "text_overlay" && <TextOverlayParams params={editParams} onChange={updateParam} />}
              {selected.variable_type === "hook_intro" && <HookParams params={editParams} onChange={updateParam} />}
              {selected.variable_type === "persistent_text" && <PersistentTextParams params={editParams} onChange={updateParam} />}
              {selected.variable_type === "color_grade" && <ColorGradeParams params={editParams} onChange={updateParam} />}
              {selected.variable_type === "speed" && <SpeedParams params={editParams} onChange={updateParam} />}

              {/* Test button (pre-process variables) */}
              {typeInfo?.hasPreProcess && testClip && (
                <button onClick={handleTest} disabled={testing}
                  className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded text-sm text-white disabled:opacity-50">
                  <FlaskConical size={14} /> {testing ? "Processing..." : "Test Variable"}
                </button>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-500">Select or create a preset to start</div>
        )}
      </div>

      {/* Right: Remotion Player Preview */}
      <div className="w-[380px] border-l border-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-800 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white">Live Preview</h2>
          {supportsDragPosition && videoSrc && (
            <span className="text-[10px] text-gray-500 uppercase tracking-wide">Drag caption to move</span>
          )}
        </div>
        <div className="flex-1 flex items-center justify-center p-4 bg-gray-950">
          {videoSrc && selected ? (
            <div
              ref={playerFrameRef}
              style={{ position: "relative", width: "100%", aspectRatio: "9 / 16", borderRadius: 12, overflow: "hidden" }}
            >
              <Player
                component={Comp}
                inputProps={playerProps}
                durationInFrames={durationInFrames}
                compositionWidth={1080}
                compositionHeight={1920}
                fps={fps}
                style={{ width: "100%", height: "100%" }}
                controls
                autoPlay={false}
              />
              {supportsDragPosition && (
                <div
                  onPointerDown={handlePositionDragStart}
                  style={{
                    position: "absolute",
                    left: `${dragPosX}%`,
                    top: `${dragPosY}%`,
                    transform: "translate(-50%, -50%)",
                    width: "70%",
                    minHeight: "12%",
                    cursor: "move",
                    border: "1.5px dashed rgba(96, 165, 250, 0.7)",
                    borderRadius: 8,
                    background: "rgba(59, 130, 246, 0.05)",
                    pointerEvents: "auto",
                    touchAction: "none",
                    zIndex: 10,
                  }}
                  title="Drag to reposition captions"
                />
              )}
            </div>
          ) : (
            <div className="text-sm text-gray-500 text-center">Upload a test clip to preview</div>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Param components ---

function ParamSlider({ label, value, onChange, min, max, step = 1 }: {
  label: string; value: number; onChange: (v: number) => void; min: number; max: number; step?: number;
}) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between"><label className="text-xs text-gray-400">{label}</label><span className="text-xs text-gray-500">{value}</span></div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={e => onChange(Number(e.target.value))} className="w-full accent-blue-500" />
    </div>
  );
}

function ParamSelect({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[];
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-gray-400">{label}</label>
      <select value={value} onChange={e => onChange(e.target.value)}
        className="w-full px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-white">
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

function ParamColor({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-gray-400">{label}</label>
      <div className="flex items-center gap-2">
        <input type="color" value={value} onChange={e => onChange(e.target.value)} className="w-8 h-8 rounded border-0 cursor-pointer" />
        <input value={value} onChange={e => onChange(e.target.value)}
          className="flex-1 px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-white font-mono" />
      </div>
    </div>
  );
}

function ParamText({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-gray-400">{label}</label>
      <input value={value} onChange={e => onChange(e.target.value)}
        className="w-full px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-white" />
    </div>
  );
}

function ParamToggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between cursor-pointer">
      <span className="text-xs text-gray-400">{label}</span>
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={`relative w-9 h-5 rounded-full transition-colors ${value ? "bg-blue-600" : "bg-gray-700"}`}
      >
        <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${value ? "translate-x-4" : ""}`} />
      </button>
    </label>
  );
}

function CaptionParams({ params, onChange }: { params: Record<string, unknown>; onChange: (k: string, v: unknown) => void }) {
  const showBackground = (params.showBackground as boolean) ?? false;
  const strokeWidth = (params.strokeWidth as number) ?? 6;
  return (
    <div className="space-y-3">
      <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide">Caption Style</h3>
      <ParamSlider label="Words per page" value={params.wordsPerPage as number || 4} onChange={v => onChange("wordsPerPage", v)} min={1} max={8} />
      <ParamSlider label="Font size" value={params.fontSize as number || 52} onChange={v => onChange("fontSize", v)} min={24} max={140} />
      <ParamColor label="Highlight color" value={params.highlightColor as string || "#22D3EE"} onChange={v => onChange("highlightColor", v)} />
      <ParamColor label="Text color" value={params.color as string || "#FFFFFF"} onChange={v => onChange("color", v)} />

      <div className="pt-2 border-t border-gray-800 space-y-3">
        <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide">Position</h3>
        <ParamSlider label="X (horizontal %)" value={(params.positionX as number) ?? 50} onChange={v => onChange("positionX", v)} min={0} max={100} />
        <ParamSlider label="Y (vertical %)" value={(params.positionY as number) ?? 88} onChange={v => onChange("positionY", v)} min={0} max={100} />
        <p className="text-xs text-gray-500">Drag the caption in the preview or use these sliders for precision.</p>
      </div>

      <div className="pt-2 border-t border-gray-800 space-y-3">
        <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide">Stroke</h3>
        <ParamSlider label="Stroke width" value={strokeWidth} onChange={v => onChange("strokeWidth", v)} min={0} max={14} />
        {strokeWidth > 0 && (
          <ParamColor label="Stroke color" value={params.strokeColor as string || "#000000"} onChange={v => onChange("strokeColor", v)} />
        )}
      </div>

      <div className="pt-2 border-t border-gray-800 space-y-3">
        <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide">Background Pill</h3>
        <ParamToggle label="Show background pill" value={showBackground} onChange={v => onChange("showBackground", v)} />
        {showBackground && (
          <ParamColor label="Pill color" value={params.backgroundColor as string || "rgba(0, 0, 0, 0.65)"} onChange={v => onChange("backgroundColor", v)} />
        )}
      </div>

      <div className="pt-2 border-t border-gray-800 space-y-3">
        <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide">Phrasing</h3>
        <ParamSlider label="Max gap (ms) before new phrase" value={(params.phraseGapMs as number) ?? 450} onChange={v => onChange("phraseGapMs", v)} min={150} max={1200} step={50} />
        <p className="text-xs text-gray-500">Shorter = tighter sentence breaks. Longer = fewer breaks. Punctuation always breaks.</p>
      </div>
    </div>
  );
}

function TextOverlayParams({ params, onChange }: { params: Record<string, unknown>; onChange: (k: string, v: unknown) => void }) {
  return (
    <div className="space-y-3">
      <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide">Text Overlay</h3>
      <ParamText label="Text" value={params.text as string || ""} onChange={v => onChange("text", v)} />
      <ParamSlider label="Font size" value={params.fontSize as number || 48} onChange={v => onChange("fontSize", v)} min={16} max={120} />
      <ParamColor label="Text color" value={params.color as string || "#FFFFFF"} onChange={v => onChange("color", v)} />
      <ParamSelect label="Position" value={params.position as string || "bottom"} onChange={v => onChange("position", v)}
        options={[{ value: "bottom", label: "Bottom" }, { value: "center", label: "Center" }, { value: "top", label: "Top" }]} />
      <ParamSelect label="Animation" value={params.animation as string || "fade"} onChange={v => onChange("animation", v)}
        options={[{ value: "fade", label: "Fade" }, { value: "slide-up", label: "Slide Up" }, { value: "none", label: "None" }]} />
    </div>
  );
}

function HookParams({ params, onChange }: { params: Record<string, unknown>; onChange: (k: string, v: unknown) => void }) {
  return (
    <div className="space-y-3">
      <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide">Hook Intro</h3>
      <ParamSelect label="Hook type" value={params.hookType as string || "question"} onChange={v => onChange("hookType", v)}
        options={[{ value: "question", label: "Question" }, { value: "stat", label: "Statistic" }, { value: "controversy", label: "Controversy" }, { value: "pattern_interrupt", label: "Pattern Interrupt" }]} />
      <ParamText label="Hook text" value={params.hookText as string || ""} onChange={v => onChange("hookText", v)} />
      <ParamText label="Subtext" value={params.hookSubtext as string || ""} onChange={v => onChange("hookSubtext", v)} />
      <ParamSlider label="Duration (s)" value={params.hookDuration as number || 3} onChange={v => onChange("hookDuration", v)} min={1} max={8} />
      <ParamSlider label="Font size" value={params.hookFontSize as number || 64} onChange={v => onChange("hookFontSize", v)} min={32} max={120} />
      <ParamColor label="Text color" value={params.hookColor as string || "#FFFFFF"} onChange={v => onChange("hookColor", v)} />
      <ParamColor label="Background" value={params.hookBackgroundColor as string || "#0F172A"} onChange={v => onChange("hookBackgroundColor", v)} />
      <ParamSelect label="Transition" value={params.transition as string || "fade"} onChange={v => onChange("transition", v)}
        options={[{ value: "fade", label: "Fade" }, { value: "slide", label: "Slide" }, { value: "zoom", label: "Zoom" }]} />
    </div>
  );
}

function PersistentTextParams({ params, onChange }: { params: Record<string, unknown>; onChange: (k: string, v: unknown) => void }) {
  const showBackground = (params.showBackground as boolean) ?? false;
  const strokeWidth = (params.strokeWidth as number) ?? 6;
  return (
    <div className="space-y-3">
      <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide">Text</h3>
      <div className="space-y-1">
        <label className="text-xs text-gray-400">Default hook text</label>
        <textarea
          value={(params.text as string) || ""}
          onChange={e => onChange("text", e.target.value)}
          rows={2}
          className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-white resize-y leading-snug focus:border-blue-500 outline-none"
          placeholder="e.g. Follow for more Paris trips"
        />
        <p className="text-[11px] text-gray-500">Per-variant text can override this when added to a production.</p>
      </div>
      <ParamSlider label="Font size" value={(params.fontSize as number) ?? 72} onChange={v => onChange("fontSize", v)} min={24} max={180} />
      <ParamSlider label="Font weight" value={(params.fontWeight as number) ?? 800} onChange={v => onChange("fontWeight", v)} min={400} max={900} step={100} />
      <ParamColor label="Text color" value={(params.color as string) || "#FFFFFF"} onChange={v => onChange("color", v)} />
      <ParamSlider label="Box width (% of frame)" value={(params.maxWidth as number) ?? 85} onChange={v => onChange("maxWidth", v)} min={30} max={100} />

      <div className="pt-2 border-t border-gray-800 space-y-3">
        <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide">Position</h3>
        <ParamSlider label="X (horizontal %)" value={(params.positionX as number) ?? 50} onChange={v => onChange("positionX", v)} min={0} max={100} />
        <ParamSlider label="Y (vertical %)" value={(params.positionY as number) ?? 15} onChange={v => onChange("positionY", v)} min={0} max={100} />
        <p className="text-xs text-gray-500">Drag the text in the preview or fine-tune with sliders.</p>
      </div>

      <div className="pt-2 border-t border-gray-800 space-y-3">
        <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide">Stroke</h3>
        <ParamSlider label="Stroke width" value={strokeWidth} onChange={v => onChange("strokeWidth", v)} min={0} max={14} />
        {strokeWidth > 0 && (
          <ParamColor label="Stroke color" value={(params.strokeColor as string) || "#000000"} onChange={v => onChange("strokeColor", v)} />
        )}
      </div>

      <div className="pt-2 border-t border-gray-800 space-y-3">
        <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide">Pill Background</h3>
        <ParamToggle label="Show pill background" value={showBackground} onChange={v => onChange("showBackground", v)} />
        {showBackground && (
          <>
            <ParamColor label="Pill color" value={(params.backgroundColor as string) || "rgba(0, 0, 0, 0.7)"} onChange={v => onChange("backgroundColor", v)} />
            <ParamSlider label="Horizontal padding" value={(params.paddingX as number) ?? 32} onChange={v => onChange("paddingX", v)} min={0} max={80} />
            <ParamSlider label="Vertical padding" value={(params.paddingY as number) ?? 16} onChange={v => onChange("paddingY", v)} min={0} max={60} />
          </>
        )}
      </div>
    </div>
  );
}

function ColorGradeParams({ params, onChange }: { params: Record<string, unknown>; onChange: (k: string, v: unknown) => void }) {
  return (
    <div className="space-y-3">
      <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide">Color Grade</h3>
      <ParamSelect label="Profile" value={params.profile as string || "cinematic_warm"} onChange={v => onChange("profile", v)}
        options={[
          { value: "cinematic_warm", label: "Cinematic Warm" }, { value: "cinematic_cool", label: "Cinematic Cool" },
          { value: "moody_dark", label: "Moody Dark" }, { value: "vibrant", label: "Vibrant" },
          { value: "vintage", label: "Vintage" }, { value: "black_and_white", label: "Black & White" },
        ]} />
      <p className="text-xs text-gray-500">Click "Test Variable" with a clip to preview the grade</p>
    </div>
  );
}

function SpeedParams({ params, onChange }: { params: Record<string, unknown>; onChange: (k: string, v: unknown) => void }) {
  return (
    <div className="space-y-3">
      <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide">Speed</h3>
      <ParamSlider label="Speed factor" value={params.speed_factor as number || 1.0} onChange={v => onChange("speed_factor", v)} min={0.25} max={4} step={0.25} />
      <p className="text-xs text-gray-500">Click "Test Variable" with a clip to preview the speed change</p>
    </div>
  );
}
