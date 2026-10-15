import { ApiClient, ApiError, type TokenStore, type Tokens } from "@/api/client";

function memoryStore(initial: Tokens | null): TokenStore & { value: Tokens | null } {
  return {
    value: initial,
    async load() {
      return this.value;
    },
    async save(tokens: Tokens) {
      this.value = tokens;
    },
    async clear() {
      this.value = null;
    },
  };
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

test("refreshes once on 401, rotates tokens and retries", async () => {
  const store = memoryStore({ accessToken: "old", refreshToken: "r1", pinChangeRequired: false });
  const calls: string[] = [];
  const fake = (async (url: string, init?: RequestInit) => {
    const auth = new Headers(init?.headers).get("Authorization");
    calls.push(`${url} ${auth ?? ""}`);
    if (url.endsWith("/v1/auth/refresh")) return json(200, { access_token: "new", refresh_token: "r2", pin_change_required: false });
    return auth === "Bearer new" ? json(200, { ok: true }) : json(401, { detail: "expired" });
  }) as typeof fetch;
  const api = new ApiClient("http://api", store, fake);
  const [a, b] = await Promise.all([api.get<{ ok: boolean }>("/v1/me"), api.get<{ ok: boolean }>("/v1/me")]);
  expect(a.ok && b.ok).toBe(true);
  expect(calls.filter((c) => c.includes("/refresh"))).toHaveLength(1);
  expect(store.value?.refreshToken).toBe("r2");
});

test("failed refresh signs out and clears tokens", async () => {
  const store = memoryStore({ accessToken: "old", refreshToken: "r1", pinChangeRequired: false });
  let signedOut = false;
  const fake = (async () => json(401, { detail: "Session expired" })) as typeof fetch;
  const api = new ApiClient("http://api", store, fake, () => {
    signedOut = true;
  });
  await expect(api.get("/v1/me")).rejects.toBeInstanceOf(ApiError);
  expect(store.value).toBeNull();
  expect(signedOut).toBe(true);
});

test("errors carry the server detail", async () => {
  const api = new ApiClient("http://api", memoryStore(null), (async () => json(409, { detail: "Not enough coins" })) as typeof fetch);
  await expect(api.post("/v1/shop/x")).rejects.toThrow("Not enough coins");
});

test("web: a reload resumes from the HttpOnly cookie without any stored token", async () => {
  const store = memoryStore(null);
  const seen: RequestInit[] = [];
  const fake = (async (url: string, init?: RequestInit) => {
    seen.push(init ?? {});
    if (url.endsWith("/v1/auth/refresh")) return json(200, { access_token: "fresh", refresh_token: null, pin_change_required: false });
    return json(200, { ok: true });
  }) as typeof fetch;
  const api = new ApiClient("http://api", store, fake, undefined, true);
  expect((await api.resume())?.accessToken).toBe("fresh");
  await api.get("/v1/me");
  const [refresh, me] = seen as [RequestInit, RequestInit];
  expect(refresh.credentials).toBe("include");
  expect(new Headers(refresh.headers).get("X-Lingard-Client")).toBe("web");
  expect(refresh.body).toBeUndefined();
  expect(me.credentials).toBeUndefined(); // the cookie is scoped to /v1/auth and only sent there
});

test("web: no live cookie means signed out, not an error", async () => {
  let signedOut = false;
  const api = new ApiClient("http://api", memoryStore(null), (async () => json(401, { detail: "Not signed in" })) as typeof fetch, () => {
    signedOut = true;
  }, true);
  expect(await api.resume()).toBeNull();
  expect(signedOut).toBe(true);
});

test("web: tabs take turns refreshing so none replays a rotated cookie", async () => {
  const order: string[] = [];
  let held = Promise.resolve();
  const locks = {
    request: (_name: string, work: () => Promise<unknown>) => {
      const run = held.then(work);
      held = run.then(() => undefined);
      return run;
    },
  };
  Object.defineProperty(globalThis.navigator, "locks", { value: locks, configurable: true });
  try {
    let n = 0;
    const fake = (async () => {
      const mine = ++n;
      order.push(`start ${mine}`);
      await new Promise((r) => setTimeout(r, 5));
      order.push(`end ${mine}`);
      return json(200, { access_token: `a${mine}`, refresh_token: null, pin_change_required: false });
    }) as typeof fetch;
    const tabA = new ApiClient("http://api", memoryStore(null), fake, undefined, true);
    const tabB = new ApiClient("http://api", memoryStore(null), fake, undefined, true);
    await Promise.all([tabA.resume(), tabB.resume()]);
    expect(order).toEqual(["start 1", "end 1", "start 2", "end 2"]);
  } finally {
    delete (globalThis.navigator as { locks?: unknown }).locks;
  }
});

test("web: a request made before resume finishes still refreshes from the cookie", async () => {
  const fake = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/v1/auth/refresh")) return json(200, { access_token: "fresh", refresh_token: null, pin_change_required: false });
    const auth = new Headers(init?.headers).get("Authorization");
    return auth === "Bearer fresh" ? json(200, { ok: true }) : json(401, { detail: "Not signed in" });
  }) as typeof fetch;
  const api = new ApiClient("http://api", memoryStore(null), fake, undefined, true);
  expect(await api.get<{ ok: boolean }>("/v1/passport")).toEqual({ ok: true });
});
