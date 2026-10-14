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
