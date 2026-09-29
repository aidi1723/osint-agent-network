const graphemeSegmenter = typeof Intl !== "undefined" && typeof Intl.Segmenter === "function"
  ? new Intl.Segmenter(undefined, { granularity: "grapheme" })
  : null;

export function compactGraphLabel(value: string, maxGraphemes: number): string {
  if (!Number.isFinite(maxGraphemes) || !Number.isInteger(maxGraphemes)) {
    throw new RangeError("maxGraphemes must be a finite integer");
  }
  if (maxGraphemes <= 0) return "";
  if (!graphemeSegmenter) return compactWithoutSegmenter(value, maxGraphemes);
  const graphemes = Array.from(graphemeSegmenter.segment(value), ({ segment }) => segment);
  if (graphemes.length <= maxGraphemes) return value;
  if (maxGraphemes === 1) return "…";
  return `${graphemes.slice(0, maxGraphemes - 1).join("")}…`;
}

export function nextSelectedNode(currentId: string | null, nextId: string): string | null {
  return currentId === nextId ? null : nextId;
}

function compactWithoutSegmenter(value: string, maxGraphemes: number): string {
  const codePoints = Array.from(value);
  if (codePoints.length <= maxGraphemes) return value;
  if (!/^[\x00-\x7f]*$/.test(value)) return "…";

  const asciiGraphemes: string[] = [];
  for (let index = 0; index < value.length; index += 1) {
    if (value[index] === "\r" && value[index + 1] === "\n") {
      asciiGraphemes.push("\r\n");
      index += 1;
    } else {
      asciiGraphemes.push(value[index]);
    }
  }
  if (asciiGraphemes.length <= maxGraphemes) return value;
  if (maxGraphemes === 1) return "…";
  return `${asciiGraphemes.slice(0, maxGraphemes - 1).join("")}…`;
}
