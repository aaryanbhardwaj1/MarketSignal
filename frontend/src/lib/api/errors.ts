/**
 * Error envelope parsing. The API returns {"error": {"code", "message", ...}} for domain
 * errors; request-validation failures still use FastAPI's default {"detail": ...} shape,
 * so both are normalised into a single ApiError.
 */

export const NETWORK_ERROR = "NETWORK_ERROR";
export const VALIDATION_ERROR = "VALIDATION_ERROR";
export const UNKNOWN_ERROR = "UNKNOWN_ERROR";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  /** The full `error` object from the envelope (e.g. carries `tombstone` on 410). */
  readonly details: Readonly<Record<string, unknown>>;

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function validationMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => {
        if (!isRecord(item)) return String(item);
        const loc = Array.isArray(item.loc) ? item.loc.filter((p) => p !== "body").join(".") : "";
        const msg = typeof item.msg === "string" ? item.msg : "invalid value";
        return loc ? `${loc}: ${msg}` : msg;
      })
      .join("; ");
  }
  return "Request validation failed";
}

/** Converts a non-2xx response body (already JSON-decoded, or null) into an ApiError. */
export function parseApiError(status: number, body: unknown, statusText = ""): ApiError {
  if (isRecord(body) && isRecord(body.error)) {
    const err = body.error;
    const code = typeof err.code === "string" && err.code ? err.code : UNKNOWN_ERROR;
    const message =
      typeof err.message === "string" && err.message ? err.message : `Request failed (${status})`;
    return new ApiError(status, code, message, { ...err });
  }
  if (isRecord(body) && "detail" in body) {
    const code = status === 422 ? VALIDATION_ERROR : UNKNOWN_ERROR;
    return new ApiError(status, code, validationMessage(body.detail), { detail: body.detail });
  }
  const suffix = statusText ? ` ${statusText}` : "";
  return new ApiError(status, UNKNOWN_ERROR, `Request failed (${status}${suffix})`);
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

/** Human-readable "CODE: message" string for any thrown value. */
export function describeError(error: unknown): { code: string; message: string } {
  if (isApiError(error)) return { code: error.code, message: error.message };
  if (error instanceof Error) return { code: UNKNOWN_ERROR, message: error.message };
  return { code: UNKNOWN_ERROR, message: String(error) };
}
