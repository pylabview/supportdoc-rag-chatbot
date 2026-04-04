export const DEFAULT_API_BASE_URL = "http://127.0.0.1:9001";

export function readApiBaseUrl() {
  const configured = import.meta.env.VITE_SUPPORTDOC_API_BASE_URL;
  if (typeof configured !== "string") {
    return DEFAULT_API_BASE_URL;
  }

  const normalized = configured.trim();
  if (!normalized) {
    return DEFAULT_API_BASE_URL;
  }

  return normalized.replace(/\/+$/, "");
}

export function buildApiUrl(apiBaseUrl, path) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${apiBaseUrl}${normalizedPath}`;
}
