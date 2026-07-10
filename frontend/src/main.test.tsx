// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const authMocks = vi.hoisted(() => ({
  loadSession: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  requestOptions: vi.fn((method: string, csrfToken?: string) => ({
    method,
    credentials: "include",
    ...(csrfToken ? { headers: { "X-CSRF-Token": csrfToken } } : {}),
  })),
}));

const apiMocks = vi.hoisted(() => ({
  fetchJson: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
}));

vi.mock("./auth", () => authMocks);
vi.mock("./api", () => apiMocks);

import { App } from "./main";

type UnauthorizedHandler = (() => void) | null;

let root: Root;
let unauthorizedHandler: UnauthorizedHandler;

function defaultApiResponse(input: RequestInfo | URL) {
  const url = String(input);
  if (url.includes("/api/tools")) return Promise.resolve({ tools: [] });
  if (url.includes("/api/investigations")) return Promise.resolve({ investigations: [] });
  if (url.includes("/api/agents")) return Promise.resolve({ agents: [] });
  if (url.includes("/api/system/status")) return Promise.resolve(null);
  return Promise.resolve({});
}

async function renderApp() {
  await act(async () => {
    root.render(<App />);
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function submitLogin(adminToken: string) {
  const input = document.querySelector<HTMLInputElement>("#admin-token");
  const form = document.querySelector<HTMLFormElement>(".admin-login-panel form");
  expect(input).not.toBeNull();
  expect(form).not.toBeNull();

  await act(async () => {
    const valueSetter = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )?.set;
    valueSetter?.call(input, adminToken);
    input?.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => {
    form?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("App browser auth shell", () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="test-root"></div>';
    root = createRoot(document.getElementById("test-root")!);
    unauthorizedHandler = null;
    authMocks.loadSession.mockReset();
    authMocks.login.mockReset();
    authMocks.logout.mockReset();
    apiMocks.fetchJson.mockReset().mockImplementation(defaultApiResponse);
    apiMocks.setUnauthorizedHandler.mockReset().mockImplementation((handler) => {
      unauthorizedHandler = handler;
    });
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
      .IS_REACT_ACT_ENVIRONMENT = true;
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  it("shows AdminLogin when authentication is required and absent", async () => {
    authMocks.loadSession.mockResolvedValue({ authenticated: false, required: true });

    await renderApp();

    expect(document.body.textContent).toContain("管理员登录");
    expect(document.querySelector(".shell")).toBeNull();
  });

  it("mounts OperationsConsole and loads initial data after successful login", async () => {
    authMocks.loadSession.mockResolvedValue({ authenticated: false, required: true });
    authMocks.login.mockResolvedValue({ authenticated: true, csrf_token: "csrf-login" });
    await renderApp();

    await submitLogin("operator-secret");

    expect(authMocks.login).toHaveBeenCalledWith("", "operator-secret");
    expect(document.querySelector(".shell")).not.toBeNull();
    expect(apiMocks.fetchJson).toHaveBeenCalledWith(
      "/api/tools",
      expect.objectContaining({ method: "GET", credentials: "include" }),
    );
  });

  it("returns to login on 401 without retrying data requests", async () => {
    authMocks.loadSession.mockResolvedValue({
      authenticated: true,
      required: true,
      csrf_token: "csrf-session",
    });
    await renderApp();
    const initialRequestCount = apiMocks.fetchJson.mock.calls.length;
    expect(unauthorizedHandler).toBeTypeOf("function");

    await act(async () => {
      unauthorizedHandler?.();
      await Promise.resolve();
    });

    expect(document.body.textContent).toContain("管理员登录");
    expect(document.querySelector(".shell")).toBeNull();
    expect(authMocks.loadSession).toHaveBeenCalledTimes(1);
    expect(apiMocks.fetchJson).toHaveBeenCalledTimes(initialRequestCount);
  });

  it("logs out an authenticated session and returns to login", async () => {
    authMocks.loadSession.mockResolvedValue({
      authenticated: true,
      required: true,
      csrf_token: "csrf-session",
    });
    authMocks.logout.mockResolvedValue({ authenticated: false });
    await renderApp();
    const logoutButton = document.querySelector<HTMLButtonElement>(
      'button[aria-label="退出登录"]',
    );
    expect(logoutButton).not.toBeNull();

    await act(async () => {
      logoutButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(authMocks.logout).toHaveBeenCalledWith("", "csrf-session");
    expect(document.body.textContent).toContain("管理员登录");
    expect(document.querySelector(".shell")).toBeNull();
  });
});
