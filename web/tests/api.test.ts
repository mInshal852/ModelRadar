import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiGet, buildQuery, load } from "@/lib/api";

const fetchMock = vi.fn();

beforeEach(() => {
  process.env.API_INTERNAL_URL = "http://api.test";
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
});
afterEach(() => vi.unstubAllGlobals());

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("buildQuery", () => {
  it("drops empty values and encodes the rest", () => {
    expect(buildQuery({ q: "a b", page: 2, empty: "", none: undefined, nil: null })).toBe(
      "?q=a+b&page=2",
    );
    expect(buildQuery()).toBe("");
  });
});

describe("apiGet", () => {
  it("calls the internal API without caching and without credentials or cookies", async () => {
    fetchMock.mockResolvedValue(json({ ok: true }));
    await apiGet("/v1/meta", { page: 1 });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/v1/meta?page=1");
    expect(init.cache).toBe("no-store");
    expect(init.credentials).toBeUndefined();
    expect(Object.keys(init.headers as Record<string, string>)).toEqual(["Accept"]);
  });

  it("maps API error bodies to ApiError", async () => {
    fetchMock.mockResolvedValue(
      json({ error: { code: "validation_error", message: "Some parameters are invalid." } }, 422),
    );
    await expect(apiGet("/v1/announcements")).rejects.toMatchObject({
      status: 422,
      code: "validation_error",
      message: "Some parameters are invalid.",
    });
  });

  it("handles an error response that is not JSON", async () => {
    fetchMock.mockResolvedValue(new Response("<html>bad gateway</html>", { status: 502 }));
    await expect(apiGet("/v1/meta")).rejects.toMatchObject({ status: 502, code: "error" });
  });

  it("reports an unreachable service", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    await expect(apiGet("/v1/meta")).rejects.toMatchObject({ status: 0, code: "unreachable" });
  });

  it("reports a missing configuration", async () => {
    delete process.env.API_INTERNAL_URL;
    await expect(apiGet("/v1/meta")).rejects.toMatchObject({ code: "not_configured" });
  });
});

describe("load", () => {
  it("returns data on success", async () => {
    fetchMock.mockResolvedValue(json({ total: 3 }));
    expect(await load<{ total: number }>("/v1/x")).toEqual({ data: { total: 3 }, error: null });
  });

  it("returns an error instead of throwing, so pages can show an error state", async () => {
    fetchMock.mockRejectedValue(new Error("boom"));
    const result = await load("/v1/x");
    expect(result.data).toBeNull();
    expect(result.error).toBeInstanceOf(ApiError);
  });
});
