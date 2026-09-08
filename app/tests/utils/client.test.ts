import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  TimeoutError,
  apiDelete,
  apiGet,
  apiPost,
  apiRequest,
} from "../../src/lib/api/client";

describe("ApiError", () => {
  it("is an Error with status and body", () => {
    const err = new ApiError(404, { detail: "not found" });
    expect(err).toBeInstanceOf(Error);
    expect(err.status).toBe(404);
    expect(err.body).toEqual({ detail: "not found" });
    expect(err.message).toBe("API Error 404");
  });
});

describe("apiGet", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns parsed JSON on 200", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ id: 1 }), { status: 200 }),
    );
    const result = await apiGet<{ id: number }>("/api/test");
    expect(result).toEqual({ id: 1 });
  });

  it("throws ApiError on non-2xx response", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "not found" }), { status: 404 }),
    );
    await expect(apiGet("/api/missing")).rejects.toBeInstanceOf(ApiError);
  });

  it("includes status code in thrown ApiError", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "server error" }), { status: 500 }),
    );
    let caught: ApiError | null = null;
    try {
      await apiGet("/api/fail");
    } catch (e) {
      if (e instanceof ApiError) caught = e;
    }
    expect(caught?.status).toBe(500);
  });

  it("handles non-JSON error body gracefully", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response("Internal Server Error", {
        status: 500,
        headers: { "Content-Type": "text/plain" },
      }),
    );
    const err = await apiGet("/api/fail").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.body).toBeNull();
  });
});

describe("apiPost", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends JSON body and returns parsed response", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ created: true }), { status: 201 }),
    );
    const result = await apiPost<{ created: boolean }>("/api/items", { name: "test" });
    expect(result).toEqual({ created: true });

    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect((init as RequestInit).method).toBe("POST");
    expect((init as RequestInit).body).toBe(JSON.stringify({ name: "test" }));
  });
});

describe("apiRequest headers, timeout, delete", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("never sends Content-Type on a bodyless GET, always sends X-Requested-With", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response("{}", { status: 200 }));
    await apiGet("/api/x");
    const headers = vi.mocked(fetch).mock.calls[0][1]!.headers as Headers;
    expect(headers.has("Content-Type")).toBe(false);
    expect(headers.get("X-Requested-With")).toBe("XMLHttpRequest");
    expect(headers.get("Accept")).toBe("application/json");
  });

  it("sets Content-Type for a string body", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response("{}", { status: 200 }));
    await apiPost("/api/x", { a: 1 });
    const headers = vi.mocked(fetch).mock.calls[0][1]!.headers as Headers;
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("leaves Content-Type unset for a FormData body", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response("{}", { status: 200 }));
    const fd = new FormData();
    fd.append("f", "v");
    await apiRequest("/api/upload", { method: "POST", body: fd });
    const headers = vi.mocked(fetch).mock.calls[0][1]!.headers as Headers;
    expect(headers.has("Content-Type")).toBe(false);
  });

  it("apiDelete issues a DELETE and resolves undefined on empty body", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response("", { status: 200 }));
    const out = await apiDelete("/api/thing/1");
    expect(out).toBeUndefined();
    expect(vi.mocked(fetch).mock.calls[0][1]!.method).toBe("DELETE");
  });

  it("throws TimeoutError when the request aborts", async () => {
    vi.mocked(fetch).mockImplementationOnce((_url, init) => {
      return new Promise((_resolve, reject) => {
        const signal = (init as RequestInit).signal!;
        signal.addEventListener("abort", () => {
          reject(new DOMException("aborted", "AbortError"));
        });
      });
    });
    await expect(apiGet("/api/slow", { timeoutMs: 5 })).rejects.toBeInstanceOf(TimeoutError);
  });
});
