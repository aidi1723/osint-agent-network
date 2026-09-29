// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthRequestError } from "../auth";
import { AdminLogin } from "./AdminLogin";

let root: Root;

async function renderAndSubmit(error: unknown) {
  const onLogin = vi.fn().mockRejectedValue(error);
  await act(async () => root.render(<AdminLogin onLogin={onLogin} />));
  const input = document.querySelector<HTMLInputElement>("#admin-token")!;
  const form = document.querySelector<HTMLFormElement>(".admin-login-panel form")!;

  await act(async () => {
    const valueSetter = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )?.set;
    valueSetter?.call(input, "operator-secret");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await Promise.resolve();
    await Promise.resolve();
  });
  return document.querySelector<HTMLElement>('[role="alert"]');
}

describe("AdminLogin errors", () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="test-root"></div>';
    root = createRoot(document.getElementById("test-root")!);
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
      .IS_REACT_ACT_ENVIRONMENT = true;
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    document.body.innerHTML = "";
  });

  it("uses non-leaking invalid credential copy for a 401", async () => {
    const alert = await renderAndSubmit(new AuthRequestError("invalid credentials", 401));

    expect(alert?.textContent).toBe("管理员凭据无效，请检查后重试。");
  });

  it("uses service copy for network failures", async () => {
    const alert = await renderAndSubmit(new TypeError("Failed to fetch"));

    expect(alert?.textContent).toBe("认证服务暂时不可用，请稍后重试。");
  });

  it("uses service copy for server failures", async () => {
    const alert = await renderAndSubmit(new AuthRequestError("server error", 500));

    expect(alert?.textContent).toBe("认证服务暂时不可用，请稍后重试。");
  });
});
