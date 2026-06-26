import { useMemo } from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";

export interface WordCaption {
  word: string;
  startMs: number;
  endMs: number;
}

interface CaptionOverlayProps {
  words: WordCaption[];
  wordsPerPage?: number;
  fontSize?: number;
  highlightColor?: string;
  color?: string;
  backgroundColor?: string;
  // Legacy coarse position. positionX/positionY override it when provided.
  position?: "bottom" | "center" | "top";
  // 0-100 percent of composition width/height, from top-left. Caption is centered on this point.
  positionX?: number;
  positionY?: number;
  fontFamily?: string;
  fontWeight?: number;
  strokeColor?: string;
  strokeWidth?: number;
  // Max ms silence between words before forcing a new phrase
  phraseGapMs?: number;
}

const SENTENCE_END = /[.!?…]$/;

/**
 * Group words into phrases bounded by punctuation or long pauses, then chunk
 * each phrase into pages of at most `wordsPerPage` words. Pages never cross
 * phrase boundaries — so one page won't mix the tail of one sentence with the
 * start of another.
 */
function buildPages(
  words: WordCaption[],
  wordsPerPage: number,
  phraseGapMs: number,
): WordCaption[][] {
  if (!words.length) return [];
  const phrases: WordCaption[][] = [];
  let current: WordCaption[] = [];
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    const prev = words[i - 1];
    const gap = prev ? w.startMs - prev.endMs : 0;
    const prevEndsSentence = prev && SENTENCE_END.test(prev.word.trim());
    if (current.length && (prevEndsSentence || gap > phraseGapMs)) {
      phrases.push(current);
      current = [];
    }
    current.push(w);
  }
  if (current.length) phrases.push(current);

  const pages: WordCaption[][] = [];
  for (const phrase of phrases) {
    for (let i = 0; i < phrase.length; i += wordsPerPage) {
      pages.push(phrase.slice(i, i + wordsPerPage));
    }
  }
  return pages;
}

export const CaptionOverlay: React.FC<CaptionOverlayProps> = ({
  words,
  wordsPerPage = 4,
  fontSize = 52,
  highlightColor = "#22D3EE",
  color = "#FFFFFF",
  backgroundColor = "transparent",
  position = "bottom",
  positionX,
  positionY,
  fontFamily = '-apple-system, "SF Pro Display", "SF Pro Text", system-ui, sans-serif',
  fontWeight = 800,
  strokeColor = "#000000",
  strokeWidth = 6,
  phraseGapMs = 450,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTimeMs = (frame / fps) * 1000;

  const pages = useMemo(
    () => buildPages(words, wordsPerPage, phraseGapMs),
    [words, wordsPerPage, phraseGapMs],
  );

  // Active page = first page whose word range contains currentTimeMs.
  const activePage = pages.find((p) => {
    const start = p[0].startMs;
    const end = p[p.length - 1].endMs;
    return currentTimeMs >= start && currentTimeMs <= end;
  });
  if (!activePage) return null;

  // Resolve position. If positionX/Y are set, use them (center-anchored).
  // Otherwise fall back to the coarse `position` enum.
  const legacyY = position === "top" ? 8 : position === "center" ? 50 : 88;
  const resolvedX = typeof positionX === "number" ? positionX : 50;
  const resolvedY = typeof positionY === "number" ? positionY : legacyY;
  const posStyle: React.CSSProperties = {
    top: `${resolvedY}%`,
    left: `${resolvedX}%`,
    right: "auto",
    bottom: "auto",
    transform: "translate(-50%, -50%)",
  };

  return (
    <div
      style={{
        position: "absolute",
        pointerEvents: "none",
        maxWidth: "90%",
        ...posStyle,
      }}
    >
      <div
        style={{
          padding: backgroundColor === "transparent" ? "0" : "10px 20px",
          borderRadius: 12,
          backgroundColor,
          textAlign: "center",
          whiteSpace: "nowrap",
        }}
      >
        {activePage.map((w, i) => {
          const isActive =
            currentTimeMs >= w.startMs && currentTimeMs <= w.endMs;
          return (
            <span
              key={w.startMs + "-" + i}
              style={{
                fontFamily,
                fontSize,
                fontWeight,
                color: isActive ? highlightColor : color,
                // Real vector stroke on the glyph outline. `paint-order: stroke fill`
                // draws the stroke BEHIND the fill so the letter body isn't pinched.
                WebkitTextStrokeWidth: strokeWidth > 0 ? `${strokeWidth}px` : undefined,
                WebkitTextStrokeColor: strokeWidth > 0 ? strokeColor : undefined,
                paintOrder: "stroke fill",
                letterSpacing: "0.01em",
                transition: "color 0.08s",
              }}
            >
              {w.word}{" "}
            </span>
          );
        })}
      </div>
    </div>
  );
};
