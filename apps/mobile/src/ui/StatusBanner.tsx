/** The one place the app shows what went wrong, at the top of every screen. While the server can't be reached: a calm
 * "Reconnecting…" that checks every few seconds and clears itself (screens reload what failed once it is back).
 * Otherwise the latest error any screen raised (``ErrorText``), with Retry when the screen offered one; a close or a
 * swipe up dismisses it. */
import Ionicons from "@expo/vector-icons/Ionicons";
import * as Haptics from "expo-haptics";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import Animated, {
  FadeInUp,
  FadeOutUp,
  LinearTransition,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { reportReachable, useOnline } from "@/api/connection";
import { API_URL } from "@/config";
import { clearError, useErrors } from "@/state/errors";
import {
  colors,
  fonts,
  MAX_WIDTH,
  radius,
  shadow,
  space,
  type,
} from "@/ui/theme";

const CHECK_EVERY_MS = 3000;
/** Below the height of a screen's back bar (``Screen``), so Back is never covered. */
const BELOW_BACK_BAR = 48;

export function StatusBanner() {
  const { t } = useTranslation();
  const online = useOnline();
  const errors = useErrors();
  const insets = useSafeAreaInsets();
  const latest = errors[errors.length - 1];
  const lift = useSharedValue(0);
  const lifted = useAnimatedStyle(() => ({
    transform: [{ translateY: Math.min(0, lift.value) }],
    opacity: 1 + Math.min(0, lift.value) / 120,
  }));
  const dismiss = (id: number) => {
    lift.value = 0;
    clearError(id);
  };
  const swipe = Gesture.Pan()
    .activeOffsetY(-8)
    .onUpdate((e) => {
      lift.value = e.translationY;
    })
    .onEnd((e) => {
      if (e.translationY < -32 && latest) runOnJS(dismiss)(latest.id);
      else lift.value = withTiming(0);
    });

  useEffect(() => {
    if (online) return;
    const timer = setInterval(() => {
      fetch(`${API_URL}/v1/health`)
        .then((r) => r.ok && reportReachable(true))
        .catch(() => undefined);
    }, CHECK_EVERY_MS);
    return () => clearInterval(timer);
  }, [online]);
  useEffect(() => {
    if (online && latest)
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
  }, [online, latest?.id, latest?.message]); // eslint-disable-line react-hooks/exhaustive-deps -- once per new error

  if (online && !latest) return null;
  return (
    <View
      pointerEvents="box-none"
      style={[styles.wrap, { top: insets.top + BELOW_BACK_BAR }]}
    >
      {!online ? (
        <Animated.View
          key="offline"
          entering={FadeInUp.duration(220)}
          exiting={FadeOutUp.duration(180)}
          style={[styles.pill, shadow(2)]}
          accessibilityRole="alert"
          accessibilityLiveRegion="polite"
        >
          <Ionicons name="cloud-offline" size={16} color={colors.accentInk} />
          <Text style={styles.pillText}>{t("app.reconnecting")}</Text>
          <ActivityIndicator size="small" color={colors.accentInk} />
        </Animated.View>
      ) : (
        latest && (
          <GestureDetector gesture={swipe}>
            <Animated.View
              key="error"
              entering={FadeInUp.duration(220)}
              exiting={FadeOutUp.duration(180)}
              layout={LinearTransition.duration(180)}
              style={[styles.card, shadow(3), lifted]}
              accessibilityRole="alert"
              accessibilityLiveRegion="assertive"
              testID="status-error"
            >
              <Ionicons
                name="alert-circle"
                size={22}
                color={colors.danger}
                style={{ marginTop: 1 }}
              />
              <View style={{ flex: 1, gap: space(1) }}>
                <Text style={[type.callout, { color: colors.ink }]}>
                  {latest.message}
                </Text>
                {(latest.onRetry || errors.length > 1) && (
                  <View style={styles.actions}>
                    {latest.onRetry && (
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel={t("app.retry")}
                        onPress={latest.onRetry}
                        hitSlop={8}
                        style={({ pressed }) => [
                          styles.retry,
                          pressed && { opacity: 0.7 },
                        ]}
                      >
                        <Ionicons
                          name="refresh"
                          size={15}
                          color={colors.accentInk}
                        />
                        <Text style={styles.retryText}>{t("app.retry")}</Text>
                      </Pressable>
                    )}
                    {errors.length > 1 && (
                      <Text style={type.caption}>
                        {t("app.moreErrors", { count: errors.length - 1 })}
                      </Text>
                    )}
                  </View>
                )}
              </View>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={t("app.close")}
                hitSlop={12}
                onPress={() => dismiss(latest.id)}
              >
                <Ionicons name="close" size={20} color={colors.muted} />
              </Pressable>
            </Animated.View>
          </GestureDetector>
        )
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: "absolute",
    left: 0,
    right: 0,
    alignItems: "center",
    paddingHorizontal: space(2),
    zIndex: 100,
  },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: space(1),
    paddingHorizontal: space(1.75),
    paddingVertical: space(1),
    borderRadius: radius.pill,
    backgroundColor: colors.ink,
  },
  pillText: {
    fontFamily: fonts.semibold,
    fontSize: 14,
    color: colors.accentInk,
  },
  card: {
    width: "100%",
    maxWidth: MAX_WIDTH,
    flexDirection: "row",
    alignItems: "flex-start",
    gap: space(1.25),
    padding: space(1.75),
    borderRadius: radius.lg,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.dangerSoft,
  },
  actions: { flexDirection: "row", alignItems: "center", gap: space(1.5) },
  retry: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    minHeight: 34,
    paddingHorizontal: space(1.5),
    borderRadius: radius.pill,
    backgroundColor: colors.accent,
  },
  retryText: {
    fontFamily: fonts.semibold,
    fontSize: 14,
    color: colors.accentInk,
  },
});
