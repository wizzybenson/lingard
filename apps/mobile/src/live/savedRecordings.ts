/** Recordings kept on the device until the server has them. A take is copied into the app's documents the moment it
 * stops, so a dropped connection (or the app closing) never costs the learner a recording: it is sent again from
 * there. Forgotten once the server answers. On the web the browser keeps the take for the page's life only. */
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Directory, File, Paths } from "expo-file-system";
import { Platform } from "react-native";

const PREFIX = "recording:";
const onWeb = Platform.OS === "web";
const memory = new Map<string, string>();

function fileFor(key: string): File {
  const folder = new Directory(Paths.document, "recordings");
  if (!folder.exists) folder.create({ intermediates: true, idempotent: true });
  return new File(folder, `${key.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 120)}.m4a`);
}

/** Keeps a fresh take under ``key`` (replacing an older one) and returns where it now lives. */
export async function keep(key: string, uri: string): Promise<string> {
  if (onWeb) {
    memory.set(key, uri);
    return uri;
  }
  const target = fileFor(key);
  if (target.exists) target.delete();
  await new File(uri).copy(target);
  await AsyncStorage.setItem(PREFIX + key, target.uri);
  return target.uri;
}

/** The take still waiting to be sent under ``key``, if any. */
export async function saved(key: string): Promise<string | null> {
  if (onWeb) return memory.get(key) ?? null;
  try {
    const uri = await AsyncStorage.getItem(PREFIX + key);
    return uri && new File(uri).exists ? uri : null;
  } catch {
    return null;
  }
}

/** The server has the take: it is no longer waiting. The file stays for "hear yourself" until the next take of the
 * same line replaces it, so storage holds at most one take per line. */
export async function sent(key: string): Promise<void> {
  if (onWeb) {
    memory.delete(key);
    return;
  }
  try {
    await AsyncStorage.removeItem(PREFIX + key);
  } catch {
    // still marked waiting: it is offered again, and sending it twice is harmless
  }
}
