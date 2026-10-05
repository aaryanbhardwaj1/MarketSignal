const DEFAULT_API_URL = "http://localhost:8000";

/** Base URL of the MarketSignal API, without a trailing slash. */
export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL).replace(/\/+$/, "");
