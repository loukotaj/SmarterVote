import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";

const { getAuth0Client, loggerError } = vi.hoisted(() => ({
  getAuth0Client: vi.fn(),
  loggerError: vi.fn(),
}));

vi.mock("$lib/auth", () => ({ getAuth0Client }));
vi.mock("$lib/utils/logger", () => ({
  logger: { error: loggerError, warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import { apiStore, fetchWithAuth, initializeAuth } from "./apiStore";

/** A fetch stub that never settles until its AbortSignal fires. */
function hangingFetch() {
  return vi.fn(
    (_url: string, options: RequestInit = {}) =>
      new Promise<Response>((_resolve, reject) => {
        options.signal?.addEventListener("abort", () => {
          const error = new Error("The operation was aborted.");
          error.name = "AbortError";
          reject(error);
        });
      }),
  );
}

function fakeAuth0(token = "tok-123") {
  return { getTokenSilently: vi.fn().mockResolvedValue(token) };
}

function resetStore() {
  apiStore.set({ auth0: null, token: "", isAuthenticated: false });
}

beforeEach(() => {
  resetStore();
  getAuth0Client.mockReset();
  loggerError.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("initializeAuth", () => {
  it("stores the client and token and marks the session authenticated", async () => {
    const auth0 = fakeAuth0("tok-abc");
    getAuth0Client.mockResolvedValue(auth0);

    const result = await initializeAuth();

    expect(result).toEqual({ auth0, token: "tok-abc" });
    expect(get(apiStore)).toEqual({
      auth0,
      token: "tok-abc",
      isAuthenticated: true,
    });
  });

  it("logs and rethrows when Auth0 cannot produce a token", async () => {
    getAuth0Client.mockRejectedValue(new Error("auth0 down"));

    await expect(initializeAuth()).rejects.toThrow("auth0 down");
    expect(loggerError).toHaveBeenCalledWith(
      "Failed to initialize auth:",
      expect.any(Error),
    );
    // A failed initialization must not leave the store claiming authentication.
    expect(get(apiStore).isAuthenticated).toBe(false);
  });
});

describe("fetchWithAuth token handling", () => {
  it("sends the stored token without re-contacting Auth0", async () => {
    apiStore.set({ auth0: null, token: "stored-tok", isAuthenticated: true });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true } as Response);
    vi.stubGlobal("fetch", fetchMock);

    await fetchWithAuth("https://api.test/races");

    expect(getAuth0Client).not.toHaveBeenCalled();
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBe("Bearer stored-tok");
  });

  it("acquires a token on cold start and writes it back to the store", async () => {
    const auth0 = fakeAuth0("fresh-tok");
    getAuth0Client.mockResolvedValue(auth0);
    const fetchMock = vi.fn().mockResolvedValue({ ok: true } as Response);
    vi.stubGlobal("fetch", fetchMock);

    await fetchWithAuth("https://api.test/races");

    expect(getAuth0Client).toHaveBeenCalledTimes(1);
    expect(get(apiStore)).toMatchObject({
      token: "fresh-tok",
      isAuthenticated: true,
    });
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBe("Bearer fresh-tok");
  });

  it("reuses an already-stored client rather than constructing a new one", async () => {
    const auth0 = fakeAuth0("refreshed");
    apiStore.set({
      auth0: auth0 as never,
      token: "",
      isAuthenticated: false,
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true } as Response));

    await fetchWithAuth("https://api.test/races");

    expect(getAuth0Client).not.toHaveBeenCalled();
    expect(auth0.getTokenSilently).toHaveBeenCalledTimes(1);
  });

  it("fails closed with a clear message when refresh fails", async () => {
    getAuth0Client.mockRejectedValue(new Error("refresh exploded"));
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchWithAuth("https://api.test/races")).rejects.toThrow(
      "Authentication token refresh failed",
    );
    // The request must never go out unauthenticated.
    expect(fetchMock).not.toHaveBeenCalled();
    expect(loggerError).toHaveBeenCalledWith(
      "Failed to refresh token:",
      expect.any(Error),
    );
  });

  it("merges the Authorization header with caller-supplied headers", async () => {
    apiStore.set({ auth0: null, token: "tok", isAuthenticated: true });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true } as Response);
    vi.stubGlobal("fetch", fetchMock);

    await fetchWithAuth("https://api.test/races", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers).toMatchObject({
      "Content-Type": "application/json",
      Authorization: "Bearer tok",
    });
    expect(init.method).toBe("POST");
  });
});

describe("fetchWithAuth timeout policy", () => {
  beforeEach(() => {
    apiStore.set({ auth0: null, token: "tok", isAuthenticated: true });
  });

  it("aborts an ordinary request after the 30s default", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", hangingFetch());

    const pending = fetchWithAuth("https://api.test/races");
    const assertion = expect(pending).rejects.toThrow(
      "Request timed out after 30 seconds: GET https://api.test/races",
    );
    await vi.advanceTimersByTimeAsync(30000);
    await assertion;
  });

  it("honours an explicit timeout over the default", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", hangingFetch());

    const pending = fetchWithAuth("https://api.test/races", {}, 5000);
    const assertion = expect(pending).rejects.toThrow(
      "Request timed out after 5 seconds",
    );
    await vi.advanceTimersByTimeAsync(5000);
    await assertion;
  });

  // Pipeline work legitimately runs for hours; a 30s abort would kill it.
  it.each([
    ["https://api.test/runs/run-1", {}],
    ["https://api.test/api/races/queue", {}],
    ["https://api.test/races/x/continue", {}],
    ["https://api.test/races/x/run", { method: "POST" }],
  ])("does not arm a timeout for long-running %s", async (url, options) => {
    vi.useFakeTimers();
    const fetchMock = hangingFetch();
    vi.stubGlobal("fetch", fetchMock);

    let settled = false;
    void fetchWithAuth(url, options as RequestInit).finally(() => {
      settled = true;
    });

    // Well past the default ceiling — a timer would have fired by now.
    await vi.advanceTimersByTimeAsync(120000);
    expect(settled).toBe(false);
    const requestInit = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(requestInit?.signal?.aborted).toBe(false);
  });

  it("treats an explicit timeout as authoritative even for long operations", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", hangingFetch());

    const pending = fetchWithAuth("https://api.test/runs/run-1", {}, 1000);
    const assertion = expect(pending).rejects.toThrow("Request timed out");
    await vi.advanceTimersByTimeAsync(1000);
    await assertion;
  });

  it("clears the timer once a response arrives", async () => {
    vi.useFakeTimers();
    const clearSpy = vi.spyOn(globalThis, "clearTimeout");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true } as Response));

    await fetchWithAuth("https://api.test/races");

    expect(clearSpy).toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("fetchWithAuth error reporting", () => {
  beforeEach(() => {
    apiStore.set({ auth0: null, token: "tok", isAuthenticated: true });
  });

  it("labels a network failure with the method and URL", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );

    await expect(
      fetchWithAuth("https://api.test/races", { method: "DELETE" }),
    ).rejects.toThrow(
      "Network request failed: DELETE https://api.test/races. Failed to fetch",
    );
  });

  it("defaults the method to GET in error text", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")));

    await expect(fetchWithAuth("https://api.test/races")).rejects.toThrow(
      "Network request failed: GET https://api.test/races. boom",
    );
  });

  it("stringifies a non-Error rejection rather than dropping it", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue("plain string failure"));

    await expect(fetchWithAuth("https://api.test/races")).rejects.toThrow(
      "plain string failure",
    );
  });

  it("clears the timer when the request fails", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")));

    await expect(fetchWithAuth("https://api.test/races")).rejects.toThrow();
    expect(vi.getTimerCount()).toBe(0);
  });
});

// The long-running path never arms a timer, so both exits have to cope with a
// null timeoutId. These are the branches an ordinary-request test cannot reach.
describe("fetchWithAuth untimed (long-running) request paths", () => {
  beforeEach(() => {
    apiStore.set({ auth0: null, token: "tok", isAuthenticated: true });
  });

  it("returns the response when no timer was armed", async () => {
    const response = { ok: true, status: 200 } as Response;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    await expect(fetchWithAuth("https://api.test/runs/run-1")).resolves.toBe(
      response,
    );
  });

  it("reports a network failure when no timer was armed", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("socket died")));

    await expect(fetchWithAuth("https://api.test/runs/run-1")).rejects.toThrow(
      "Network request failed: GET https://api.test/runs/run-1. socket died",
    );
  });

  it("describes an abort with no deadline as a signal abort, not a timeout", async () => {
    const aborted = new Error("The operation was aborted.");
    aborted.name = "AbortError";
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(aborted));

    await expect(fetchWithAuth("https://api.test/runs/run-1")).rejects.toThrow(
      "Request timed out due to abort signal: GET https://api.test/runs/run-1",
    );
  });
});
