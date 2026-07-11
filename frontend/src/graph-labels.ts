export function compactGraphLabel(value: string, maxCodePoints: number): string {
  if (maxCodePoints <= 0) return "";
  const codePoints = Array.from(value);
  if (codePoints.length <= maxCodePoints) return value;
  if (maxCodePoints === 1) return "…";
  return `${codePoints.slice(0, maxCodePoints - 1).join("")}…`;
}

export function nextSelectedNode(currentId: string | null, nextId: string): string | null {
  return currentId === nextId ? null : nextId;
}
