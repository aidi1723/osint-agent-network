import React from "react";
import type { DataMetric } from "../types";

export function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <article className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

export function MiniMetrics({ metrics }: { metrics: DataMetric[] }) {
  return (
    <div className="mini-metrics">
      {metrics.map((m) => (
        <Metric key={m.label} label={m.label} value={m.value} />
      ))}
    </div>
  );
}
