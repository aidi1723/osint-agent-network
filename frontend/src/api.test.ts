import { describe, expect, it, vi } from "vitest";
import {
  createSupplyChainInvestigation,
  fetchInvestigationIntelligence,
  fetchJson,
  fetchSupplyChainData,
} from "./api";

describe("fetchJson", () => {
  it("throws backend detail for non-2xx responses", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "unauthorized read request" }),
    });

    await expect(fetchJson("/api/investigations", {}, fetchImpl)).rejects.toThrow("unauthorized read request");
    expect(fetchImpl).toHaveBeenCalledWith("/api/investigations", {});
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
      fetchSupplyChainData("/api", "Example Inc", { Authorization: "Bearer admin" }, fetchImpl),
    ).rejects.toThrow("missing customs credentials");
    expect(fetchImpl).toHaveBeenCalledWith("/api/api/customs/supply-chain", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer admin",
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
      fetchInvestigationIntelligence("", "task-1", { Authorization: "Bearer admin" }, fetchImpl),
    ).rejects.toThrow("unauthorized read request");
  });

  it("throws backend detail when creating a supply-chain investigation fails", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "unauthorized management request" }),
    });

    await expect(
      createSupplyChainInvestigation("", "Partner LLC", { Authorization: "Bearer admin" }, fetchImpl),
    ).rejects.toThrow("unauthorized management request");
  });
});
