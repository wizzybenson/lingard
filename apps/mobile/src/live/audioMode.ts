/** Lingard is something to listen to: lesson lines, exam recordings and the golden self play with the iPhone's silent
 * switch on, as spoken-word apps do (iOS mutes app audio in silent mode unless the app asks). */
import { setAudioModeAsync } from "expo-audio";
import { Platform } from "react-native";

export async function playAloud(): Promise<void> {
  if (Platform.OS === "web") return;
  await setAudioModeAsync({ playsInSilentMode: true }).catch(() => undefined);
}
