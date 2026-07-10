export type AuthSession = {
  authenticated: boolean;
  required?: boolean;
  role?: string;
  csrf_token?: string;
};

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export class AuthRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "AuthRequestError";
    this.status = status;
  }
}

export function requestOptions(method: string, csrfToken?: string): RequestInit {
  const normalizedMethod = method.toUpperCase();
  if (normalizedMethod === "GET" || normalizedMethod === "HEAD") {
    return { method: normalizedMethod, credentials: "include" };
  }

  return {
    method: normalizedMethod,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
    },
  };
}

export async function loadSession(
  apiBase: string,
  fetchImpl: FetchLike = fetch,
): Promise<AuthSession> {
  return authRequest(`${apiBase}/api/auth/session`, requestOptions("GET"), fetchImpl);
}

export async function login(
  apiBase: string,
  adminToken: string,
  fetchImpl: FetchLike = fetch,
): Promise<AuthSession> {
  return authRequest(
    `${apiBase}/api/auth/login`,
    {
      ...requestOptions("POST"),
      body: JSON.stringify({ admin_token: adminToken }),
    },
    fetchImpl,
  );
}

export async function logout(
  apiBase: string,
  csrfToken: string,
  fetchImpl: FetchLike = fetch,
): Promise<AuthSession> {
  return authRequest(
    `${apiBase}/api/auth/logout`,
    {
      ...requestOptions("POST", csrfToken),
      body: JSON.stringify({}),
    },
    fetchImpl,
  );
}

export function authEnvironmentKeys(): string[] {
  return ["VITE_API_BASE_URL"];
}

async function authRequest(
  input: RequestInfo | URL,
  init: RequestInit,
  fetchImpl: FetchLike,
): Promise<AuthSession> {
  const response = await fetchImpl(input, init);
  const payload = await response.json().catch(() => ({})) as Partial<AuthSession> & { detail?: unknown };
  if (!response.ok) {
    const message = typeof payload.detail === "string" && payload.detail.trim()
      ? payload.detail
      : `Authentication request failed with status ${response.status}`;
    throw new AuthRequestError(message, response.status);
  }
  return payload as AuthSession;
}
