const graphemeSegmenter = typeof Intl !== "undefined" && typeof Intl.Segmenter === "function"
  ? new Intl.Segmenter(undefined, { granularity: "grapheme" })
  : null;

export function compactGraphLabel(value: string, maxGraphemes: number): string {
  if (!Number.isFinite(maxGraphemes) || !Number.isInteger(maxGraphemes)) {
    throw new RangeError("maxGraphemes must be a finite integer");
  }
  if (maxGraphemes <= 0) return "";
  const graphemes = splitGraphemes(value);
  if (graphemes.length <= maxGraphemes) return value;
  if (maxGraphemes === 1) return "…";
  return `${graphemes.slice(0, maxGraphemes - 1).join("")}…`;
}

export function nextSelectedNode(currentId: string | null, nextId: string): string | null {
  return currentId === nextId ? null : nextId;
}

function splitGraphemes(value: string): string[] {
  if (graphemeSegmenter) {
    return Array.from(graphemeSegmenter.segment(value), ({ segment }) => segment);
  }

  const clusters: string[] = [];
  for (const character of Array.from(value)) {
    const lastIndex = clusters.length - 1;
    if (lastIndex < 0) {
      clusters.push(character);
    } else if (isGraphemeExtension(character)) {
      clusters[lastIndex] += character;
    } else if (character === "\u200d") {
      clusters[lastIndex] += character;
    } else if (clusters[lastIndex].endsWith("\u200d")) {
      clusters[lastIndex] += character;
    } else if (isRegionalIndicator(character) && trailingRegionalIndicatorCount(clusters[lastIndex]) % 2 === 1) {
      clusters[lastIndex] += character;
    } else {
      clusters.push(character);
    }
  }
  return clusters;
}

function isGraphemeExtension(character: string): boolean {
  const codePoint = character.codePointAt(0) ?? 0;
  return /\p{Mark}/u.test(character)
    || codePoint === 0xfe0e
    || codePoint === 0xfe0f
    || (codePoint >= 0xe0100 && codePoint <= 0xe01ef)
    || (codePoint >= 0x1f3fb && codePoint <= 0x1f3ff);
}

function isRegionalIndicator(character: string): boolean {
  const codePoint = character.codePointAt(0) ?? 0;
  return codePoint >= 0x1f1e6 && codePoint <= 0x1f1ff;
}

function trailingRegionalIndicatorCount(cluster: string): number {
  let count = 0;
  for (const character of Array.from(cluster).reverse()) {
    if (!isRegionalIndicator(character)) break;
    count += 1;
  }
  return count;
}
