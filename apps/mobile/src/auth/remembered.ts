/** Sign-in suggestions on this device: the names that signed in here, and each one's PIN behind Face ID.
 *
 * iOS only offers to save passwords for apps tied to a website, so Lingard keeps its own. Names are not secret
 * (AsyncStorage); PINs live in the keychain with ``requireAuthentication``, so reading one asks for Face ID / the device
 * passcode every time. A one-time PIN is never saved: the PIN chosen after it is. The web keeps names only.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

const NAMES = "lingard.names";
const PIN_NAMES = "lingard.pinNames";
const KEEP = 3;

const key = (name: string): string => name.trim().toLocaleLowerCase();
/** One keychain item per name; keychain keys allow only letters, digits, "." "-" and "_", so the name is hex-encoded. */
const pinKey = (name: string): string =>
  `lingard.pin.${Array.from(key(name), (c) => c.codePointAt(0)!.toString(16)).join("-")}`;

async function list(storageKey: string): Promise<string[]> {
  try {
    return JSON.parse((await AsyncStorage.getItem(storageKey)) ?? "[]") as string[];
  } catch {
    return [];
  }
}

/** Names that signed in on this device, most recent first. */
export function rememberedNames(): Promise<string[]> {
  return list(NAMES);
}

/** Whether a PIN is saved for this name (asks for nothing: only the list of names is read). */
export async function hasSavedPin(name: string): Promise<boolean> {
  return (await list(PIN_NAMES)).includes(key(name));
}

/** Remember the name, and its PIN behind Face ID (not on the web). Failures are ignored: suggestions are a comfort. */
export async function remember(name: string, pin: string | null): Promise<void> {
  try {
    const names = [name.trim(), ...(await list(NAMES)).filter((n) => key(n) !== key(name))].slice(0, KEEP);
    await AsyncStorage.setItem(NAMES, JSON.stringify(names));
    if (pin === null || Platform.OS === "web") return;
    await SecureStore.setItemAsync(pinKey(name), pin, {
      requireAuthentication: true,
      keychainAccessible: SecureStore.WHEN_PASSCODE_SET_THIS_DEVICE_ONLY,
    });
    const saved = [key(name), ...(await list(PIN_NAMES)).filter((n) => n !== key(name))];
    await AsyncStorage.setItem(PIN_NAMES, JSON.stringify(saved));
  } catch {
    // no passcode on the device, or storage unavailable: the learner types the PIN as before
  }
}

/** The saved PIN for this name, after Face ID; null when there is none or the learner cancels. */
export async function savedPin(name: string): Promise<string | null> {
  if (Platform.OS === "web") return null;
  try {
    return await SecureStore.getItemAsync(pinKey(name), { requireAuthentication: true, authenticationPrompt: "Lingard" });
  } catch {
    return null;
  }
}
