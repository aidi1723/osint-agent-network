import type { IntelligenceData, Investigation, SupplyChainData } from "./types";

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type UnauthorizedHandler = (() => void) | null;

let unauthorizedHandler: UnauthorizedHandler = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler): void {
  unauthorizedHandler = handler;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function fetchJson<T = unknown>(
  input: RequestInfo | URL,
  init?: RequestInit,
  fetchImpl: FetchLike = fetch,
): Promise<T> {
  const response = await fetchImpl(input, { ...init, credentials: "include" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof payload.detail === "string" && payload.detail.trim()
      ? payload.detail
      : `Request failed with status ${response.status}`;
    if (response.status === 401) unauthorizedHandler?.();
    throw new ApiError(message, response.status);
  }
  return payload as T;
}

export function fetchSupplyChainData(
  apiBase: string,
  company: string,
  headers?: Record<string, string>,
  fetchImpl: FetchLike = fetch,
): Promise<SupplyChainData> {
  return fetchJson<SupplyChainData>(
    `${apiBase}/api/customs/supply-chain`,
    {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(headers || {}),
      },
      body: JSON.stringify({ company }),
    },
    fetchImpl,
  );
}

export function createSupplyChainInvestigation(
  apiBase: string,
  companyName: string,
  headers?: Record<string, string>,
  fetchImpl: FetchLike = fetch,
): Promise<Investigation> {
  return fetchJson<Investigation>(
    `${apiBase}/api/investigations`,
    {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(headers || {}),
      },
      body: JSON.stringify({
        name: `供应链调查: ${companyName}`,
        seed_type: "company",
        seed_value: companyName,
        strategy: "standard",
      }),
    },
    fetchImpl,
  );
}

export function fetchInvestigationIntelligence(
  apiBase: string,
  investigationId: string,
  headers?: Record<string, string>,
  fetchImpl: FetchLike = fetch,
): Promise<IntelligenceData> {
  return fetchJson<IntelligenceData>(
    `${apiBase}/api/investigations/${investigationId}/intelligence`,
    { credentials: "include", headers: headers || {} },
    fetchImpl,
  );
}
