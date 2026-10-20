/** A small speaker that says one line (a model sentence, a correction, a word) in a native voice. The audio is
 * fetched only when tapped, so a lesson with many lines opens at once and costs nothing until a line is heard. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import * as Haptics from "expo-haptics";
import { useState } from "react";
import { ActivityIndicator, Pressable } from "react-native";

import type { ApiClient } from "@/api/client";
import { colors } from "@/ui/theme";

export function SpeakButton({ api, path, label, size = 20 }: { api: ApiClient; path: string; label: string; size?: number }) {
  const player = useAudioPlayer(null);
  const status = useAudioPlayerStatus(player);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  const say = async () => {
    setLoading(true);
    setFailed(false);
    try {
      player.replace(await api.mediaSource(path));
      player.seekTo(0);
      player.play();
    } catch {
      setFailed(true);
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} hitSlop={10} onPress={() => void say()} style={{ width: size + 8, alignItems: "center" }}>
      {loading ? (
        <ActivityIndicator size="small" color={colors.accent} />
      ) : (
        <Ionicons name={failed ? "volume-mute-outline" : status.playing ? "volume-high" : "volume-medium-outline"} size={size} color={failed ? colors.muted : colors.accent} />
      )}
    </Pressable>
  );
}
