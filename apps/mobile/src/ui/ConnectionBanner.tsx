/** One calm line at the top while the server can't be reached, checking every few seconds until it is back; the screens
 * underneath keep what they showed and reload what failed once it returns. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import Animated, { FadeInUp, FadeOutUp } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { reportReachable, useOnline } from "@/api/connection";
import { API_URL } from "@/config";
import { colors, fonts, radius, shadow, space } from "@/ui/theme";

const CHECK_EVERY_MS = 3000;

export function ConnectionBanner() {
  const { t } = useTranslation();
  const online = useOnline();
  const insets = useSafeAreaInsets();
  useEffect(() => {
    if (online) return;
    const timer = setInterval(() => {
      fetch(`${API_URL}/v1/health`)
        .then((r) => r.ok && reportReachable(true))
        .catch(() => undefined);
    }, CHECK_EVERY_MS);
    return () => clearInterval(timer);
  }, [online]);
  if (online) return null;
  return (
    <Animated.View
      entering={FadeInUp.duration(220)}
      exiting={FadeOutUp.duration(180)}
      pointerEvents="none"
      style={[styles.wrap, { top: insets.top + space(0.5) }]}
      accessibilityLiveRegion="polite"
      accessibilityRole="alert"
    >
      <View style={[styles.pill, shadow(2)]}>
        <Ionicons name="cloud-offline" size={16} color={colors.accentInk} />
        <Text style={styles.text}>{t("app.reconnecting")}</Text>
        <ActivityIndicator size="small" color={colors.accentInk} />
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrap: { position: "absolute", left: 0, right: 0, alignItems: "center", zIndex: 100 },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: space(1),
    paddingHorizontal: space(1.75),
    paddingVertical: space(1),
    borderRadius: radius.pill,
    backgroundColor: colors.ink,
  },
  text: { fontFamily: fonts.semibold, fontSize: 14, color: colors.accentInk },
});
