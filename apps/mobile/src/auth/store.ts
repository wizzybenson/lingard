/** Refresh tokens live in the OS keychain (SecureStore); biometrics unlock them, the PIN is re-asked after 30 days. */
import * as LocalAuthentication from "expo-local-authentication";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

import type { TokenStore, Tokens } from "@/api/client";

const KEY = "lingard.tokens";
const PIN_AT = "lingard.pinVerifiedAt";
export const PIN_REVERIFY_DAYS = 30;

const memory = new Map<string, string>();

async function getItem(key: string): Promise<string | null> {
  if (Platform.OS === "web") return memory.get(key) ?? null; // web: access token only, the refresh token is a cookie
  // An unreadable keychain (locked before first unlock, or a build without keychain access) means "no saved
  // session": the learner signs in again instead of the app hanging on its boot screen.
  return SecureStore.getItemAsync(key).catch(() => null);
}

async function setItem(key: string, value: string): Promise<void> {
  if (Platform.OS === "web") {
    memory.set(key, value);
    return;
  }
  await SecureStore.setItemAsync(key, value, { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY });
}

async function deleteItem(key: string): Promise<void> {
  if (Platform.OS === "web") {
    memory.delete(key);
    return;
  }
  await SecureStore.deleteItemAsync(key);
}

export const secureTokenStore: TokenStore = {
  async load(): Promise<Tokens | null> {
    const raw = await getItem(KEY);
    return raw ? (JSON.parse(raw) as Tokens) : null;
  },
  async save(tokens: Tokens): Promise<void> {
    await setItem(KEY, JSON.stringify(tokens));
  },
  async clear(): Promise<void> {
    await deleteItem(KEY);
  },
};

export async function markPinVerified(now: Date = new Date()): Promise<void> {
  await setItem(PIN_AT, now.toISOString());
}

export function pinStillFresh(verifiedAt: string | null, now: Date = new Date()): boolean {
  if (!verifiedAt) return false;
  return now.getTime() - new Date(verifiedAt).getTime() < PIN_REVERIFY_DAYS * 86_400_000;
}

/** True when a saved session exists, the PIN is fresh, and the device owner passes Face ID / fingerprint. */
export async function unlockWithBiometrics(): Promise<boolean> {
  if (Platform.OS === "web") return false;
  const [tokens, verifiedAt] = await Promise.all([secureTokenStore.load(), getItem(PIN_AT)]);
  if (!tokens || !pinStillFresh(verifiedAt)) return false;
  if (!(await LocalAuthentication.hasHardwareAsync()) || !(await LocalAuthentication.isEnrolledAsync())) return false;
  const result = await LocalAuthentication.authenticateAsync({ promptMessage: "Lingard" });
  return result.success;
}
