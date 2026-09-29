import { describe, expect, it, vi } from "vitest";
import {
  AuthRequestError,
  authEnvironmentKeys,
  loadSession,
  login,
  logout,
  requestOptions,
} from "./auth";

describe("browser authentication", () => {
  it("uses credentials and csrf without a bearer token", () => {
    expect(requestOptions("POST", "csrf-1")).toEqual({
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": "csrf-1",
      },
    });
    expect(JSON.stringify(requestOptions("POST", "csrf-1"))).not.toContain("Authorization");
  });

  it("omits mutation csrf when no token is present", () => {
    expect(requestOptions("POST")).toEqual({
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
    });
  });

  it("keeps read requests credentialed without json headers", () => {
    expect(requestOptions("GET", "csrf-unused")).toEqual({
      method: "GET",
      credentials: "include",
    });
  });

  it("loads the current browser session with credentials", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({
      authenticated: true,
      required: true,
      role: "administrator",
      csrf_token: "csrf-fresh",
    }), { status: 200, headers: { "Content-Type": "application/json" } }));

    await expect(loadSession("/control", fetchImpl)).resolves.toEqual({
      authenticated: true,
      required: true,
      role: "administrator",
      csrf_token: "csrf-fresh",
    });
    expect(fetchImpl).toHaveBeenCalledWith("/control/api/auth/session", {
      method: "GET",
      credentials: "include",
    });
  });

  it("rejects authenticated session and login responses without csrf", async () => {
    const missingCsrf = () => new Response(JSON.stringify({
      authenticated: true,
      required: true,
    }), { status: 200, headers: { "Content-Type": "application/json" } });

    await expect(loadSession("", vi.fn(async () => missingCsrf()))).rejects.toEqual(
      new AuthRequestError("invalid authentication response", 502),
    );
    await expect(login("", "operator-secret", vi.fn(async () => missingCsrf()))).rejects.toEqual(
      new AuthRequestError("invalid authentication response", 502),
    );
  });

  it("preserves development bypass when authentication is not required", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({
      authenticated: false,
      required: false,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));

    await expect(loadSession("", fetchImpl)).resolves.toEqual({
      authenticated: false,
      required: false,
    });
  });

  it("logs in and out using credentialed json mutations", async () => {
    const loginFetch = vi.fn(async () => new Response(JSON.stringify({
      authenticated: true,
      csrf_token: "csrf-login",
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    const logoutFetch = vi.fn(async () => new Response(JSON.stringify({
      authenticated: false,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));

    await expect(login("", "operator-secret", loginFetch)).resolves.toEqual({
      authenticated: true,
      csrf_token: "csrf-login",
    });
    expect(loginFetch).toHaveBeenCalledWith("/api/auth/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ admin_token: "operator-secret" }),
    });

    await expect(logout("", "csrf-login", logoutFetch)).resolves.toEqual({
      authenticated: false,
    });
    expect(logoutFetch).toHaveBeenCalledWith("/api/auth/logout", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": "csrf-login",
      },
      body: JSON.stringify({}),
    });
  });

  it("preserves status on authentication failures", async () => {
    const fetchImpl = vi.fn(async () => new Response(
      JSON.stringify({ detail: "invalid credentials" }),
      { status: 401, headers: { "Content-Type": "application/json" } },
    ));

    await expect(login("", "wrong", fetchImpl)).rejects.toEqual(
      new AuthRequestError("invalid credentials", 401),
    );
  });

  it("does not expose a Vite token contract", () => {
    expect(authEnvironmentKeys()).toEqual(["VITE_API_BASE_URL"]);
    expect(authEnvironmentKeys()).not.toContain("VITE_ADMIN_API_TOKEN");
  });
});
