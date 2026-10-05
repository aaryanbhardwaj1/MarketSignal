import { API_BASE_URL } from "./config";
import { ApiError, NETWORK_ERROR, parseApiError } from "./errors";

type QueryValue = string | number | undefined | null;

export interface RequestOptions {
  method?: "GET" | "POST" | "DELETE";
  query?: Record<string, QueryValue>;
  json?: unknown;
  form?: FormData;
  signal?: AbortSignal;
}

export function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = `${API_BASE_URL}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

async function readJson(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

export interface ApiResponse<T> {
  status: number;
  data: T;
}

/** Fetch wrapper: JSON in/out, throws ApiError for transport failures and non-2xx statuses. */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<ApiResponse<T>> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let body: BodyInit | undefined;
  if (options.form) {
    body = options.form;
  } else if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  }

  let res: Response;
  try {
    res = await fetch(buildUrl(path, options.query), {
      method: options.method ?? "GET",
      headers,
      body,
      signal: options.signal,
      cache: "no-store",
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, NETWORK_ERROR, `Cannot reach the API at ${API_BASE_URL}`);
  }

  const payload = await readJson(res);
  if (!res.ok) throw parseApiError(res.status, payload, res.statusText);
  return { status: res.status, data: payload as T };
}

export async function apiGet<T>(path: string, options: Omit<RequestOptions, "method"> = {}): Promise<T> {
  return (await apiRequest<T>(path, options)).data;
}
