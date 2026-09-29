import React from "react";
import { Archive, RefreshCcw, RotateCcw, Trash2, XCircle } from "lucide-react";
import type { Investigation } from "../types";

type Action = "cancel" | "reopen" | "retry" | "archive" | "delete";

interface TaskActionsProps {
  item: Investigation;
  onAction: (id: string, action: Action) => void;
}

export function TaskActions({ item, onAction }: TaskActionsProps) {
  function handleClick(event: React.MouseEvent, action: Action) {
    event.stopPropagation();
    onAction(item.id, action);
  }

  if (item.status === "ARCHIVED") {
    return (
      <div className="row-actions">
        <button type="button" className="secondary-button" onClick={(e) => handleClick(e, "reopen")}>
          <RotateCcw size={16} />恢复
        </button>
        <button type="button" className="danger-button" onClick={(e) => handleClick(e, "delete")}>
          <Trash2 size={16} />删除
        </button>
      </div>
    );
  }

  if (item.status === "COMPLETED") {
    return (
      <div className="row-actions">
        <button type="button" className="secondary-button" onClick={(e) => handleClick(e, "reopen")}>
          <RotateCcw size={16} />重开
        </button>
        <button type="button" className="secondary-button" onClick={(e) => handleClick(e, "archive")}>
          <Archive size={16} />归档
        </button>
      </div>
    );
  }

  if (["FAILED", "PARTIAL_FAILED", "CANCELLED"].includes(item.status)) {
    return (
      <div className="row-actions">
        <button type="button" className="secondary-button" onClick={(e) => handleClick(e, "retry")}>
          <RefreshCcw size={16} />重试
        </button>
        <button type="button" className="secondary-button" onClick={(e) => handleClick(e, "reopen")}>
          <RotateCcw size={16} />重开
        </button>
        <button type="button" className="secondary-button" onClick={(e) => handleClick(e, "archive")}>
          <Archive size={16} />归档
        </button>
        <button type="button" className="danger-button" onClick={(e) => handleClick(e, "delete")}>
          <Trash2 size={16} />删除
        </button>
      </div>
    );
  }

  return (
    <div className="row-actions">
      <button type="button" className="danger-button" onClick={(e) => handleClick(e, "cancel")}>
        <XCircle size={16} />取消
      </button>
    </div>
  );
}
