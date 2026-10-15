/** Auth context: the API client, sign-in state and the PIN-change gate. */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Platform } from "react-native";

import { ApiClient, type Tokens } from "@/api/client";
import { markPinVerified, secureTokenStore, unlockWithBiometrics } from "@/auth/store";
import { API_URL } from "@/config";

type Status = "booting" | "signedOut" | "locked" | "signedIn";

interface AuthValue {
  api: ApiClient;
  status: Status;
  pinChangeRequired: boolean;
  signIn(name: string, pin: string): Promise<void>;
  redeem(code: string, name: string, pin: string): Promise<void>;
  unlock(): Promise<boolean>;
  signOut(): Promise<void>;
  pinChanged(): void;
}

const AuthContext = createContext<AuthValue | null>(null);
const DEVICE_LABEL = `${Platform.OS} device`;
const WEB = Platform.OS === "web";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("booting");
  const [pinChangeRequired, setPinChangeRequired] = useState(false);
  const api = useMemo(
    () => new ApiClient(API_URL, secureTokenStore, undefined, () => setStatus("signedOut"), WEB),
    [],
  );

  useEffect(() => {
    if (WEB) {
      // The refresh cookie survives a reload; the server enforces the 30-day PIN rule when it is used.
      void api.resume().then((tokens) => {
        if (tokens) setPinChangeRequired(tokens.pinChangeRequired);
        setStatus(tokens ? "signedIn" : "signedOut");
      });
      return;
    }
    void secureTokenStore.load().then((tokens) => setStatus(tokens ? "locked" : "signedOut"));
  }, [api]);

  const accept = useCallback(async (tokens: Tokens) => {
    await markPinVerified();
    setPinChangeRequired(tokens.pinChangeRequired);
    setStatus("signedIn");
  }, []);

  const value: AuthValue = {
    api,
    status,
    pinChangeRequired,
    signIn: async (name, pin) => accept(await api.signIn(name, pin, DEVICE_LABEL)),
    redeem: async (code, name, pin) => accept(await api.redeemInvite(code, name, pin, DEVICE_LABEL)),
    unlock: async () => {
      const ok = await unlockWithBiometrics();
      if (ok) setStatus("signedIn");
      return ok;
    },
    signOut: async () => {
      await api.signOut();
      setStatus("signedOut");
    },
    pinChanged: () => setPinChangeRequired(false),
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth outside AuthProvider");
  return value;
}

export function useApi(): ApiClient {
  return useAuth().api;
}
