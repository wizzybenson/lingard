/** Auth context: the API client, sign-in state and the PIN-change gate. */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Platform } from "react-native";

import { ApiClient, type Tokens } from "@/api/client";
import { remember } from "@/auth/remembered";
import { markPinVerified, secureTokenStore, unlockWithBiometrics } from "@/auth/store";
import { API_URL } from "@/config";

type Status = "booting" | "signedOut" | "locked" | "signedIn";

interface AuthValue {
  api: ApiClient;
  status: Status;
  pinChangeRequired: boolean;
  /** The PIN just used to sign in when it must be changed, held in memory only, so the learner isn't asked twice. */
  signInPin: string | null;
  signIn(name: string, pin: string): Promise<void>;
  redeem(code: string, name: string, pin: string): Promise<void>;
  unlock(): Promise<boolean>;
  signOut(): Promise<void>;
  /** The new PIN is saved as this device's suggestion for the name that signed in. */
  pinChanged(newPin: string): void;
}

const AuthContext = createContext<AuthValue | null>(null);
const DEVICE_LABEL = `${Platform.OS} device`;
const WEB = Platform.OS === "web";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("booting");
  const [pinChangeRequired, setPinChangeRequired] = useState(false);
  const [signInPin, setSignInPin] = useState<string | null>(null);
  const [signInName, setSignInName] = useState<string | null>(null);
  const api = useMemo(
    () =>
      new ApiClient(
        API_URL,
        secureTokenStore,
        undefined,
        () => setStatus("signedOut"),
        WEB,
        () => setPinChangeRequired(true),
      ),
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
    signInPin,
    signIn: async (name, pin) => {
      const tokens = await api.signIn(name, pin, DEVICE_LABEL);
      setSignInPin(tokens.pinChangeRequired ? pin : null);
      setSignInName(name);
      void remember(name, tokens.pinChangeRequired ? null : pin); // a one-time PIN is never offered again
      await accept(tokens);
    },
    redeem: async (code, name, pin) => {
      await accept(await api.redeemInvite(code, name, pin, DEVICE_LABEL));
      void remember(name, pin);
    },
    unlock: async () => {
      const ok = await unlockWithBiometrics();
      if (ok) setStatus("signedIn");
      return ok;
    },
    signOut: async () => {
      await api.signOut();
      setSignInPin(null);
      setStatus("signedOut");
    },
    pinChanged: (newPin) => {
      setPinChangeRequired(false);
      setSignInPin(null);
      if (signInName) void remember(signInName, newPin);
    },
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
