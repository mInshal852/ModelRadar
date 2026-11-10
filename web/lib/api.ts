/**
 * Server-side client for the read-only ModelRadar API.
 *
 * Only server components call it (the browser never talks to the API directly), using the
 * internal address in API_INTERNAL_URL. Nothing about the visitor is forwarded.
 */

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Params = Record<string, string | number | undefined | null>;

export function buildQuery(params: Params = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export async function apiGet<T>(path: string, params: Params = {}): Promise<T> {
  const base = process.env.API_INTERNAL_URL;
  if (!base) throw new ApiError(0, "not_configured", "The data service address is not configured.");

  let response: Response;
  try {
    response = await fetch(`${base}${path}${buildQuery(params)}`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(8000),
    });
  } catch {
    throw new ApiError(0, "unreachable", "The data service did not respond.");
  }

  if (!response.ok) {
    let code = "error";
    let message = "The data service returned an error.";
    try {
      const body = (await response.json()) as { error?: { code?: string; message?: string } };
      code = body.error?.code ?? code;
      message = body.error?.message ?? message;
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(response.status, code, message);
  }
  return (await response.json()) as T;
}

export type Loaded<T> = { data: T; error: null } | { data: null; error: ApiError };

/** Load data for a page without throwing, so the page can render an error state in place. */
export async function load<T>(path: string, params: Params = {}): Promise<Loaded<T>> {
  try {
    return { data: await apiGet<T>(path, params), error: null };
  } catch (error) {
    if (error instanceof ApiError) return { data: null, error };
    return { data: null, error: new ApiError(0, "unexpected", "Something went wrong.") };
  }
}
