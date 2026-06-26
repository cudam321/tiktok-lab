import {
  AbsoluteFill,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { CaptionOverlay, WordCaption } from "./CaptionOverlay";

// NOTE: Each props interface below includes `[key: string]: unknown` because
// Remotion's <Composition> requires props to extend Record<string, unknown>.
// The named fields still narrow correctly; the index signature just permits
// untyped extras on the object.

// --- VariablePreview ---
export interface VariablePreviewProps {
  [key: string]: unknown;
  videoSrc: string;
}

export const VariablePreview: React.FC<VariablePreviewProps> = ({ videoSrc }) => (
  <AbsoluteFill style={{ backgroundColor: "#000" }}>
    {videoSrc && (
      <OffthreadVideo
        src={videoSrc}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    )}
  </AbsoluteFill>
);

// --- VariableCaptions ---
export interface VariableCaptionsProps {
  [key: string]: unknown;
  videoSrc: string;
  captions: WordCaption[];
  wordsPerPage?: number;
  fontSize?: number;
  highlightColor?: string;
  backgroundColor?: string;
  showBackground?: boolean;
  color?: string;
  position?: "bottom" | "center" | "top";
  positionX?: number;
  positionY?: number;
  fontFamily?: string;
  fontWeight?: number;
  strokeColor?: string;
  strokeWidth?: number;
  phraseGapMs?: number;
}

export const VariableCaptions: React.FC<VariableCaptionsProps> = ({
  videoSrc,
  captions,
  wordsPerPage = 4,
  fontSize = 52,
  highlightColor = "#22D3EE",
  backgroundColor = "rgba(0, 0, 0, 0.65)",
  showBackground = false,
  color = "#FFFFFF",
  position = "bottom",
  positionX,
  positionY,
  fontFamily,
  fontWeight,
  strokeColor,
  strokeWidth,
  phraseGapMs,
}) => (
  <AbsoluteFill style={{ backgroundColor: "#000" }}>
    {videoSrc && (
      <OffthreadVideo
        src={videoSrc}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    )}
    <CaptionOverlay
      words={captions}
      wordsPerPage={wordsPerPage}
      fontSize={fontSize}
      highlightColor={highlightColor}
      backgroundColor={showBackground ? backgroundColor : "transparent"}
      color={color}
      position={position}
      positionX={positionX}
      positionY={positionY}
      fontFamily={fontFamily}
      fontWeight={fontWeight}
      strokeColor={strokeColor}
      strokeWidth={strokeWidth}
      phraseGapMs={phraseGapMs}
    />
  </AbsoluteFill>
);

// --- VariableTextOverlay ---
export interface TimedTextLayerProps {
  text: string;
  font?: string;
  fontSize?: number;
  fontWeight?: number;
  color?: string;
  backgroundColor?: string;
  position?: "bottom" | "center" | "top";
  animation?: "fade" | "slide-up" | "none";
  inSeconds?: number;
  outSeconds?: number;
}

export interface VariableTextOverlayProps extends TimedTextLayerProps {
  [key: string]: unknown;
  videoSrc: string;
}

const TextContent: React.FC<{
  text: string;
  font: string;
  fontSize: number;
  fontWeight: number;
  color: string;
  backgroundColor: string;
  position: string;
  animation: string;
}> = ({ text, font, fontSize, fontWeight, color, backgroundColor, position, animation }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  let opacity = 1;
  let translateY = 0;

  if (animation === "fade") {
    opacity =
      interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" }) *
      interpolate(frame, [durationInFrames - 15, durationInFrames], [1, 0], { extrapolateLeft: "clamp" });
  } else if (animation === "slide-up") {
    translateY = interpolate(frame, [0, 20], [60, 0], { extrapolateRight: "clamp" });
    opacity =
      interpolate(frame, [0, 10], [0, 1], { extrapolateRight: "clamp" }) *
      interpolate(frame, [durationInFrames - 10, durationInFrames], [1, 0], { extrapolateLeft: "clamp" });
  }

  const posStyle: React.CSSProperties =
    position === "top" ? { top: 100 } :
    position === "center" ? { top: "50%", transform: `translateY(-50%) translateY(${translateY}px)` } :
    { bottom: 200 };

  if (position !== "center") {
    posStyle.transform = `translateY(${translateY}px)`;
  }

  return (
    <div
      style={{
        position: "absolute",
        left: 40,
        right: 40,
        ...posStyle,
        opacity,
        padding: "20px 32px",
        borderRadius: 12,
        backgroundColor,
        display: "flex",
        justifyContent: "center",
      }}
    >
      <span style={{ fontFamily: font, fontSize, fontWeight, color, textAlign: "center", lineHeight: 1.3 }}>
        {text}
      </span>
    </div>
  );
};

// Layer-only: the Sequence-wrapped text content, composable in VariantComposer.
export const TimedTextLayer: React.FC<TimedTextLayerProps> = ({
  text,
  font = "Inter",
  fontSize = 48,
  fontWeight = 700,
  color = "#FFFFFF",
  backgroundColor = "rgba(0, 0, 0, 0.7)",
  position = "bottom",
  animation = "fade",
  inSeconds = 0,
  outSeconds,
}) => {
  const { fps, durationInFrames } = useVideoConfig();
  const from = Math.round(inSeconds * fps);
  const dur = outSeconds ? Math.round((outSeconds - inSeconds) * fps) : durationInFrames - from;
  return (
    <Sequence from={from} durationInFrames={dur}>
      <TextContent
        text={text}
        font={font}
        fontSize={fontSize}
        fontWeight={fontWeight}
        color={color}
        backgroundColor={backgroundColor}
        position={position}
        animation={animation}
      />
    </Sequence>
  );
};

export const VariableTextOverlay: React.FC<VariableTextOverlayProps> = ({
  videoSrc,
  text,
  font = "Inter",
  fontSize = 48,
  fontWeight = 700,
  color = "#FFFFFF",
  backgroundColor = "rgba(0, 0, 0, 0.7)",
  position = "bottom",
  animation = "fade",
  inSeconds = 0,
  outSeconds,
}) => {
  const { fps, durationInFrames } = useVideoConfig();
  const from = Math.round(inSeconds * fps);
  const dur = outSeconds ? Math.round((outSeconds - inSeconds) * fps) : durationInFrames - from;

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {videoSrc && (
        <OffthreadVideo
          src={videoSrc}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      )}
      <Sequence from={from} durationInFrames={dur}>
        <TextContent
          text={text}
          font={font}
          fontSize={fontSize}
          fontWeight={fontWeight}
          color={color}
          backgroundColor={backgroundColor}
          position={position}
          animation={animation}
        />
      </Sequence>
    </AbsoluteFill>
  );
};

// --- VariablePersistentText ---
// Text overlay that stays on screen for the ENTIRE video duration. Used for
// hook text, CTAs, brand mentions — things that should never disappear.
// Distinct from VariableTextOverlay (timed) and VariableHook (intro card).

// Clean layer-only prop interface (no index signature) — the destructured
// fields stay typed. The composition-level interface below adds videoSrc +
// index signature for Remotion's <Composition> requirement.
export interface PersistentTextLayerProps {
  text: string;
  positionX?: number;
  positionY?: number;
  fontSize?: number;
  fontFamily?: string;
  fontWeight?: number;
  color?: string;
  strokeColor?: string;
  strokeWidth?: number;
  maxWidth?: number;
  showBackground?: boolean;
  backgroundColor?: string;
  paddingX?: number;
  paddingY?: number;
}

export interface VariablePersistentTextProps extends PersistentTextLayerProps {
  [key: string]: unknown;
  videoSrc: string;
}

// Layer-only version (no video, no AbsoluteFill wrapper) — composable inside
// VariantComposer. The wrapped version below plays standalone in Workshop.
export const PersistentTextLayer: React.FC<PersistentTextLayerProps> = ({
  text,
  positionX = 50,
  positionY = 15,
  fontSize = 72,
  fontFamily = '-apple-system, "SF Pro Display", "SF Pro Text", system-ui, sans-serif',
  fontWeight = 800,
  color = "#FFFFFF",
  strokeColor = "#000000",
  strokeWidth = 6,
  maxWidth = 85,
  showBackground = false,
  backgroundColor = "rgba(0, 0, 0, 0.7)",
  paddingX = 32,
  paddingY = 16,
}) => {
  const pillBg = showBackground ? backgroundColor : "transparent";
  return (
    <div
      style={{
        position: "absolute",
        left: `${positionX}%`,
        top: `${positionY}%`,
        transform: "translate(-50%, -50%)",
        maxWidth: `${maxWidth}%`,
        pointerEvents: "none",
        display: "flex",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          padding: showBackground ? `${paddingY}px ${paddingX}px` : 0,
          borderRadius: 16,
          backgroundColor: pillBg,
          textAlign: "center",
        }}
      >
        <span
          style={{
            fontFamily,
            fontSize,
            fontWeight,
            color,
            lineHeight: 1.15,
            display: "inline-block",
            WebkitTextStrokeWidth: strokeWidth > 0 ? `${strokeWidth}px` : undefined,
            WebkitTextStrokeColor: strokeWidth > 0 ? strokeColor : undefined,
            paintOrder: "stroke fill",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {text}
        </span>
      </div>
    </div>
  );
};

export const VariablePersistentText: React.FC<VariablePersistentTextProps> = ({
  videoSrc,
  ...layerProps
}) => (
  <AbsoluteFill style={{ backgroundColor: "#000" }}>
    {videoSrc && (
      <OffthreadVideo
        src={videoSrc}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    )}
    <PersistentTextLayer {...layerProps} />
  </AbsoluteFill>
);

// --- VariableHook ---
export interface VariableHookProps {
  [key: string]: unknown;
  videoSrc: string;
  hookType: "question" | "stat" | "controversy" | "pattern_interrupt";
  hookText: string;
  hookSubtext?: string;
  hookDuration?: number;
  hookColor?: string;
  hookBackgroundColor?: string;
  hookFontSize?: number;
  transition?: "fade" | "slide" | "zoom";
}

const HookCard: React.FC<{
  hookType: string;
  hookText: string;
  hookSubtext?: string;
  hookColor: string;
  hookBackgroundColor: string;
  hookFontSize: number;
}> = ({ hookType, hookText, hookSubtext, hookColor, hookBackgroundColor, hookFontSize }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const textOpacity = interpolate(frame, [8, 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const textScale = spring({ frame: frame - 5, fps, config: { damping: 15, stiffness: 100, mass: 1 } });

  const emoji =
    hookType === "question" ? "🤔" :
    hookType === "stat" ? "📊" :
    hookType === "controversy" ? "🔥" : "⚡";

  return (
    <AbsoluteFill
      style={{
        backgroundColor: hookBackgroundColor,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
        padding: 60,
      }}
    >
      <div style={{ fontSize: hookFontSize * 1.5, opacity: textOpacity, transform: `scale(${textScale})`, marginBottom: 30 }}>
        {emoji}
      </div>
      <div
        style={{
          fontFamily: "Inter, sans-serif",
          fontSize: hookFontSize,
          fontWeight: 800,
          color: hookColor,
          textAlign: "center",
          lineHeight: 1.2,
          opacity: textOpacity,
          transform: `scale(${textScale})`,
          maxWidth: "90%",
        }}
      >
        {hookText}
      </div>
      {hookSubtext && (
        <div
          style={{
            fontFamily: "Inter, sans-serif",
            fontSize: hookFontSize * 0.5,
            color: hookColor,
            opacity: textOpacity * 0.7,
            marginTop: 20,
            textAlign: "center",
          }}
        >
          {hookSubtext}
        </div>
      )}
    </AbsoluteFill>
  );
};

export const VariableHook: React.FC<VariableHookProps> = ({
  videoSrc,
  hookType,
  hookText,
  hookSubtext,
  hookDuration = 3,
  hookColor = "#FFFFFF",
  hookBackgroundColor = "#0F172A",
  hookFontSize = 64,
  transition = "fade",
}) => {
  const { fps } = useVideoConfig();
  const hookFrames = Math.round(hookDuration * fps);
  const transitionFrames = Math.round(0.5 * fps);

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      <Sequence from={hookFrames - transitionFrames}>
        {videoSrc && (
          <OffthreadVideo
            src={videoSrc}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        )}
      </Sequence>
      <Sequence durationInFrames={hookFrames}>
        <HookTransition transition={transition} transitionFrames={transitionFrames}>
          <HookCard
            hookType={hookType}
            hookText={hookText}
            hookSubtext={hookSubtext}
            hookColor={hookColor}
            hookBackgroundColor={hookBackgroundColor}
            hookFontSize={hookFontSize}
          />
        </HookTransition>
      </Sequence>
    </AbsoluteFill>
  );
};

const HookTransition: React.FC<{
  transition: string;
  transitionFrames: number;
  children: React.ReactNode;
}> = ({ transition, transitionFrames, children }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const exitStart = durationInFrames - transitionFrames;
  let style: React.CSSProperties = {};

  if (transition === "fade") {
    style.opacity = interpolate(frame, [exitStart, durationInFrames], [1, 0], {
      extrapolateLeft: "clamp", extrapolateRight: "clamp",
    });
  } else if (transition === "slide") {
    style.transform = `translateY(${interpolate(frame, [exitStart, durationInFrames], [0, -100], {
      extrapolateLeft: "clamp", extrapolateRight: "clamp",
    })}%)`;
  } else if (transition === "zoom") {
    const s = interpolate(frame, [exitStart, durationInFrames], [1, 1.5], {
      extrapolateLeft: "clamp", extrapolateRight: "clamp",
    });
    style.opacity = interpolate(frame, [exitStart, durationInFrames], [1, 0], {
      extrapolateLeft: "clamp", extrapolateRight: "clamp",
    });
    style.transform = `scale(${s})`;
  }

  return <AbsoluteFill style={style}>{children}</AbsoluteFill>;
};

// --- VariantComposer ---
// Multi-variable variant renderer. Stacks overlay layers on top of the video
// in the order defined by `variables`. Used by the Production pipeline when a
// variant contains more than one variable.
//
// The backend injects `captions` (the production's canonical transcript) at
// render time; any variable of type "captions" uses that word list automatically.
// Pre-process variables (color_grade, speed, edit_pace) are NOT represented
// here — they run as ffmpeg passes before Remotion and produce the videoSrc.

export interface VariantComposerVariable {
  type: string;
  params: Record<string, unknown>;
}

export interface VariantComposerProps {
  [key: string]: unknown;
  videoSrc: string;
  captions?: WordCaption[];
  variables: VariantComposerVariable[];
}

export const VariantComposer: React.FC<VariantComposerProps> = ({
  videoSrc,
  captions = [],
  variables = [],
}) => (
  <AbsoluteFill style={{ backgroundColor: "#000" }}>
    {videoSrc && (
      <OffthreadVideo
        src={videoSrc}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    )}
    {variables.map((v, i) => {
      const key = `${v.type}-${i}`;
      const p = v.params || {};
      if (v.type === "persistent_text") {
        return (
          <PersistentTextLayer key={key} {...(p as unknown as PersistentTextLayerProps)} />
        );
      }
      if (v.type === "text_overlay") {
        return (
          <TimedTextLayer key={key} {...(p as unknown as TimedTextLayerProps)} />
        );
      }
      if (v.type === "captions") {
        return (
          <CaptionOverlay key={key} words={captions} {...(p as Record<string, never>)} />
        );
      }
      // Unknown / non-overlay type (color_grade, speed, edit_pace, hook_intro):
      // nothing to render inside the composer — pre-process handled before
      // Remotion, and hook_intro isn't supported in multi-variable mode yet.
      return null;
    })}
  </AbsoluteFill>
);
