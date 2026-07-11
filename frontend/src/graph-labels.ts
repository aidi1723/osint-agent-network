const graphemeSegmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });

export function compactGraphLabel(value: string, maxCodePoints: number): string {
  if (maxCodePoints <= 0) return "";
  const graphemes = Array.from(graphemeSegmenter.segment(value), ({ segment }) => segment);
  if (graphemes.length <= maxCodePoints) return value;
  if (maxCodePoints === 1) return "…";
  return `${graphemes.slice(0, maxCodePoints - 1).join("")}…`;
}

export function nextSelectedNode(currentId: string | null, nextId: string): string | null {
  return currentId === nextId ? null : nextId;
}
