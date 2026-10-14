/** Typed API client: bearer auth, one shared refresh in flight, rotation of the refresh token. */

export interface Tokens {
  accessToken: string;
  refreshToken: string;
  pinChangeRequired: boolean;
}

export interface TokenStore {
  load(): Promise<Tokens | null>;
  save(tokens: Tokens): Promise<void>;
  clear(): Promise<void>;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

type Fetch = typeof fetch;

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  pin_change_required: boolean;
}

export function tokensFrom(body: TokenResponse): Tokens {
  return {
    accessToken: body.access_token,
    refreshToken: body.refresh_token,
    pinChangeRequired: body.pin_change_required,
  };
}

export class ApiClient {
  private refreshing: Promise<Tokens | null> | null = null;

  constructor(
    private readonly baseUrl: string,
    private readonly store: TokenStore,
    private readonly fetchImpl: Fetch = (input, init) => fetch(input, init), // browsers reject an unbound fetch
    private readonly onSignedOut: () => void = () => {},
  ) {}

  private async raw(path: string, init: RequestInit, token?: string): Promise<Response> {
    const headers = new Headers(init.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
    return this.fetchImpl(`${this.baseUrl}${path}`, { ...init, headers });
  }

  private async refresh(): Promise<Tokens | null> {
    this.refreshing ??= (async () => {
      const current = await this.store.load();
      if (!current) return null;
      const response = await this.raw("/v1/auth/refresh", {
        method: "POST",
        body: JSON.stringify({ refresh_token: current.refreshToken }),
      });
      if (!response.ok) {
        await this.store.clear();
        this.onSignedOut();
        return null;
      }
      const tokens = tokensFrom((await response.json()) as TokenResponse);
      await this.store.save(tokens);
      return tokens;
    })().finally(() => {
      this.refreshing = null;
    });
    return this.refreshing;
  }

  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.checked(path, init);
    return (response.status === 204 ? undefined : await response.json()) as T;
  }

  /** A text resource, such as an SVG layer. */
  async text(path: string): Promise<string> {
    return (await this.checked(path, {})).text();
  }

  private async checked(path: string, init: RequestInit): Promise<Response> {
    let tokens = await this.store.load();
    let response = await this.raw(path, init, tokens?.accessToken);
    if (response.status === 401 && tokens) {
      tokens = await this.refresh();
      if (!tokens) throw new ApiError(401, "Please sign in again.");
      response = await this.raw(path, init, tokens.accessToken);
    }
    if (!response.ok) {
      let detail = response.statusText;
      try {
        detail = ((await response.json()) as { detail?: string }).detail ?? detail;
      } catch {
        // non-JSON error body
      }
      throw new ApiError(response.status, detail);
    }
    return response;
  }

  /** For media players that fetch by URL themselves (listening items, golden-self audio). */
  async mediaSource(path: string): Promise<{ uri: string; headers: Record<string, string> }> {
    const tokens = await this.store.load();
    return { uri: `${this.baseUrl}${path}`, headers: tokens ? { Authorization: `Bearer ${tokens.accessToken}` } : {} };
  }

  get<T>(path: string): Promise<T> {
    return this.request<T>(path);
  }

  post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
  }

  /** Multipart upload (recordings). React Native accepts ``{ uri, name, type }`` file parts; the web needs a Blob. */
  postForm<T>(path: string, form: FormData): Promise<T> {
    return this.request<T>(path, { method: "POST", body: form });
  }

  patch<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
  }

  async signIn(displayName: string, pin: string, deviceLabel: string): Promise<Tokens> {
    const response = await this.raw("/v1/auth/sign-in", {
      method: "POST",
      body: JSON.stringify({ display_name: displayName, pin, device_label: deviceLabel }),
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as { detail?: string };
      throw new ApiError(response.status, body.detail ?? "Sign-in failed");
    }
    const tokens = tokensFrom((await response.json()) as TokenResponse);
    await this.store.save(tokens);
    return tokens;
  }

  async redeemInvite(code: string, displayName: string, pin: string, deviceLabel: string): Promise<Tokens> {
    const response = await this.raw("/v1/auth/redeem-invite", {
      method: "POST",
      body: JSON.stringify({ invite_code: code, display_name: displayName, pin, device_label: deviceLabel }),
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as { detail?: string };
      throw new ApiError(response.status, body.detail ?? "Invite failed");
    }
    const tokens = tokensFrom((await response.json()) as TokenResponse);
    await this.store.save(tokens);
    return tokens;
  }

  async signOut(): Promise<void> {
    try {
      await this.post("/v1/auth/sign-out");
    } finally {
      await this.store.clear();
      this.onSignedOut();
    }
  }
}
