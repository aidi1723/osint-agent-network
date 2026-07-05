import React from "react";

export function DataRow({ title, meta, body }: { title: string; meta: string; body?: string }) {
  return (
    <article className="evidence-row">
      <code>{title}</code>
      <span>{meta}</span>
      {body ? <p>{body}</p> : null}
    </article>
  );
}
