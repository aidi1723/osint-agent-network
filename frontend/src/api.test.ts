import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  createSupplyChainInvestigation,
  fetchInvestigationIntelligence,
  fetchJson,
  fetchSupplyChainData,
  setUnauthorizedHandler,
} from "./api";

describe("fetchJson", () => {
  it("notifies the auth shell once for a 401 response", async () => {
    const onUnauthorized = vi.fn();
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "unauthorized read request" }),
    });
    setUnauthorizedHandler(onUnauthorized);

    await expect(fetchJson("/api/agents", {}, fetchImpl)).rejects.toThrow("unauthorized read request");

    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    setUnauthorizedHandler(null);
  });

  it("throws backend detail for non-2xx responses", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "unauthorized read request" }),
    });

    await expect(fetchJson("/api/investigations", {}, fetchImpl)).rejects.toEqual(
      new ApiError("unauthorized read request", 401),
    );
    expect(fetchImpl).toHaveBeenCalledWith("/api/investigations", { credentials: "include" });
  });

  it("returns parsed json for ok responses", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ investigations: [] }),
    });

    await expect(fetchJson("/api/investigations", {}, fetchImpl)).resolves.toEqual({ investigations: [] });
  });

  it("throws backend detail when supply-chain query fails", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: "missing customs credentials" }),
    });

    await expect(
      fetchSupplyChainData("/api", "Example Inc", { "X-CSRF-Token": "csrf-1" }, fetchImpl),
    ).rejects.toThrow("missing customs credentials");
    expect(fetchImpl).toHaveBeenCalledWith("/api/api/customs/supply-chain", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": "csrf-1",
      },
      body: JSON.stringify({ company: "Example Inc" }),
    });
  });

  it("throws backend detail when intelligence aggregation fails", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "unauthorized read request" }),
    });

    await expect(
      fetchInvestigationIntelligence("", "task-1", undefined, fetchImpl),
    ).rejects.toThrow("unauthorized read request");
    expect(fetchImpl).toHaveBeenCalledWith("/api/investigations/task-1/intelligence", {
      credentials: "include",
      headers: {},
    });
  });

  it("throws backend detail when creating a supply-chain investigation fails", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "unauthorized management request" }),
    });

    await expect(
      createSupplyChainInvestigation("", "Partner LLC", { "X-CSRF-Token": "csrf-2" }, fetchImpl),
    ).rejects.toThrow("unauthorized management request");
    expect(fetchImpl).toHaveBeenCalledWith("/api/investigations", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": "csrf-2",
      },
      body: JSON.stringify({
        name: "供应链调查: Partner LLC",
        seed_type: "company",
        seed_value: "Partner LLC",
        strategy: "standard",
      }),
    });
  });
});
