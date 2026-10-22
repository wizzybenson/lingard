/** The end of every activity: the next stop of today's path, with why, one tap away, so a finished lesson, review round
 * or drill never ends on a dead stop (decision 0029). When the day's path is done it says so and offers home. */
import Ionicons from "@expo/vector-icons/Ionicons";
import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ActivityIndicator, I18nManager, Pressable, StyleSheet, Text, View } from "react-native";
import Animated, { FadeInUp } from "react-native-reanimated";

import type { PathStop, Today } from "@/api/types";
import { openStop, STOP_ICONS, stopTitle, stopWhy } from "@/home/stops";
import { useApi } from "@/state/auth";
import { useResource } from "@/state/resource";
import { IconBubble } from "@/ui/kit";
import { colors, radius, shadow, space, type } from "@/ui/theme";

/** ``after``: the kind of stop just finished, skipped even if the server hasn't counted it yet. */
export function UpNext({ after }: { after: PathStop["kind"] }) {
  const { t } = useTranslation();
  const api = useApi();
  const today = useResource(() => api.get<Today>("/v1/today"), [api]);
  const [opening, setOpening] = useState(false);
  if (!today.data) return null;
  const next = today.data.path.find((s) => !s.done && s.kind !== after);
  const go = () => {
    void Haptics.selectionAsync();
    if (!next) return router.navigate("/(tabs)/city");
    setOpening(true);
    void openStop(api, next).finally(() => setOpening(false));
  };
  return (
    <Animated.View entering={FadeInUp.delay(200).springify().damping(16)}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={next ? `${t("path.upNext")}: ${stopTitle(t, next)}` : t("path.backHome")}
        onPress={go}
        disabled={opening}
        style={({ pressed }) => [styles.card, shadow(2), pressed && { transform: [{ scale: 0.98 }] }]}
      >
        <IconBubble name={next ? STOP_ICONS[next.kind] : "sparkles"} tone={next ? "accent" : "sunset"} size={44} />
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={type.overline}>{next ? t("path.upNextMinutes", { minutes: next.minutes }) : t("path.allDone")}</Text>
          <Text style={type.headline} numberOfLines={2}>
            {next ? stopTitle(t, next) : t("path.celebrate")}
          </Text>
          {next && (
            <Text style={type.caption} numberOfLines={2}>
              {stopWhy(t, next)}
            </Text>
          )}
        </View>
        {opening ? (
          <ActivityIndicator color={colors.accent} />
        ) : (
          <View style={styles.go}>
            <Ionicons name={I18nManager.isRTL ? "arrow-back" : "arrow-forward"} size={18} color={colors.accentInk} />
          </View>
        )}
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: space(1.5),
    padding: space(2),
    borderRadius: radius.lg,
    backgroundColor: colors.card,
  },
  go: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.accent, alignItems: "center", justifyContent: "center" },
});
