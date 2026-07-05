const ACTIVE_INVESTIGATION_STATUSES = new Set(["OPEN", "CLAIMED", "RUNNING", "STALE_CLAIM"]);
const REVIEWABLE_INVESTIGATION_STATUSES = new Set(["NEEDS_REVIEW", "COMPLETED", "PARTIAL_FAILED"]);

export function selectedTaskRowClassName(taskId: string, selectedTaskId: string | null) {
  return selectedTaskId === taskId ? "selected-row" : "";
}

export function isActiveInvestigationStatus(status: string) {
  return ACTIVE_INVESTIGATION_STATUSES.has(status);
}

export function isReviewableInvestigationStatus(status: string) {
  return REVIEWABLE_INVESTIGATION_STATUSES.has(status);
}

export function sanitizeReportHtml(html: string) {
  const allowedTags = new Set([
    "a",
    "blockquote",
    "br",
    "code",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
  ]);
  const globalAttrs = new Set(["class", "title"]);
  const tagAttrs: Record<string, Set<string>> = {
    a: new Set(["href"]),
    img: new Set(["alt", "src"]),
    td: new Set(["colspan", "rowspan"]),
    th: new Set(["colspan", "rowspan"]),
  };

  const isSafeUrl = (value: string) => {
    const trimmed = value.trim().replace(/[\u0000-\u001F\u007F\s]+/g, "");
    if (!trimmed) return false;
    if (trimmed.startsWith("#") || trimmed.startsWith("/") || trimmed.startsWith("./") || trimmed.startsWith("../")) return true;
    try {
      const parsed = new URL(trimmed, window.location.origin);
      return ["http:", "https:", "mailto:", "tel:"].includes(parsed.protocol);
    } catch {
      return false;
    }
  };

  const cleanNode = (node: Node) => {
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const element = node as HTMLElement;
    const tagName = element.tagName.toLowerCase();

    if (!allowedTags.has(tagName)) {
      element.remove();
      return;
    }

    for (const attr of Array.from(element.attributes)) {
      const attrName = attr.name.toLowerCase();
      const allowedForTag = tagAttrs[tagName]?.has(attrName) ?? false;
      if (attrName.startsWith("on") || (!globalAttrs.has(attrName) && !allowedForTag)) {
        element.removeAttribute(attr.name);
        continue;
      }
      if ((attrName === "href" || attrName === "src") && !isSafeUrl(attr.value)) {
        element.removeAttribute(attr.name);
      }
    }

    for (const child of Array.from(element.childNodes)) {
      cleanNode(child);
    }
  };

  if (typeof DOMParser === "undefined") {
    return "";
  }

  const document = new DOMParser().parseFromString(html, "text/html");
  for (const child of Array.from(document.body.childNodes)) {
    cleanNode(child);
  }
  return document.body.innerHTML;
}
