import Constants from "expo-constants";
import { Platform } from "react-native";

const extra = (Constants.expoConfig?.extra ?? {}) as { apiUrl?: string };

const LOOPBACK = new Set(["localhost", "127.0.0.1", "[::1]"]);

/** On a phone, "localhost" is the phone itself. In development the computer serving the bundle also runs the API and
 * LiveKit, so a loopback URL is pointed at that computer's LAN address (``devHost``, e.g. "192.168.1.20:8081").
 * Any other URL, and every URL on the web, is left alone. */
export function reachable(url: string, devHost: string | null | undefined, platform: string = Platform.OS): string {
  if (platform === "web" || !devHost) return url;
  const host = devHost.split(":")[0];
  if (!host || LOOPBACK.has(host)) return url;
  const parsed = url.match(/^(\w+:\/\/)([^/:]+|\[[^\]]+\])(.*)$/);
  if (!parsed || !LOOPBACK.has(parsed[2]!)) return url;
  return `${parsed[1]}${host}${parsed[3]}`;
}

/** Where Metro is serving from, in development builds only. */
export const DEV_HOST: string | null = __DEV__ ? (Constants.expoConfig?.hostUri ?? null) : null;

export const API_URL: string = reachable(process.env.EXPO_PUBLIC_API_URL ?? extra.apiUrl ?? "http://localhost:58000", DEV_HOST);
