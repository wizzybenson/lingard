/** Today's path (decision 0029): the few things worth doing today as stops on a line, chosen by the coach from what the
 * learner has shown. Only the stop to do now is open, with why it was picked in one sentence and one button; the others
 * are a single line each, and any of them can be tapped out of order. Done stops stay, ticked, so the day shows its
 * progress. */
import Ionicons from "@expo/vector-icons/Ionicons";
import * as Haptics from "expo-haptics";
import { LinearGradient } from "expo-linear-gradient";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ActivityIndicator, I18nManager, Pressable, StyleSheet, Text, View } from "react-native";
import Animated, { FadeIn, FadeInDown, LinearTransition, ZoomIn } from "react-native-reanimated";

import type { PathStop } from "@/api/types";
import { openStop, STOP_ICONS, stopTitle, stopWhy } from "@/home/stops";
import { useApi } from "@/state/auth";
import { colors, fonts, gradients, radius, shadow, space, type } from "@/ui/theme";

const SPRING = LinearTransition.springify().damping(18).stiffness(160);

const RAIL = 28;
const NODE_TOP = space(1.5);
/** The middle of a stop's dot: the line runs from the first dot's middle to the last's. */
const NODE_MID = NODE_TOP + RAIL / 2;

export function TodayPath({
  stops,
  storyLabel,
  storyBusy,
  onStory,
  coach,
}: {
  stops: PathStop[];
  /** The learning coach's state: "thinking" while it tailors the day, "ai" once it has. */
  coach: "ai" | "thinking" | "rules";
  /** "Begin day 7" or "Continue day 7": the story stop's button. */
  storyLabel: string;
  storyBusy: boolean;
  onStory: () => void;
}) {
  const { t } = useTranslation();
  const api = useApi();
  const [opening, setOpening] = useState<string | null>(null);
  const current = stops.findIndex((s) => !s.done);
  const done = stops.filter((s) => s.done).length;
  const minutes = stops.filter((s) => !s.done).reduce((sum, s) => sum + s.minutes, 0);

  // The day's last stop ticked: a small celebration, felt as well as seen, once.
  const finished = done === stops.length;
  const wasFinished = useRef(finished);
  useEffect(() => {
    if (finished && !wasFinished.current) void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    wasFinished.current = finished;
  }, [finished]);

  const go = (stop: PathStop) => {
    void Haptics.selectionAsync();
    setOpening(stop.kind);
    void openStop(api, stop, onStory).finally(() => setOpening(null));
  };
  const title = (stop: PathStop) => stopTitle(t, stop, storyLabel);
  const why = (stop: PathStop) => stopWhy(t, stop);
  const action = (stop: PathStop) => (stop.kind === "story" ? storyLabel : t(`path.${stop.kind}.action`));
  const busy = (stop: PathStop) => (stop.kind === "story" ? storyBusy : opening === stop.kind && stop.kind !== "warmup");

  return (
    <View style={{ gap: space(1) }}>
      <View style={styles.header}>
        <Text accessibilityRole="header" style={[type.overline, { flex: 1 }]}>
          {t("path.title")}
        </Text>
        <Text style={type.caption} accessibilityLabel={t("path.progress", { done, total: stops.length })}>
          {done === stops.length ? t("path.allDone") : t("path.left", { done, total: stops.length, minutes })}
        </Text>
      </View>
      {coach !== "rules" && (
        <Animated.View key={coach} entering={FadeIn.duration(400)} style={styles.coach}>
          {coach === "thinking" ? <ActivityIndicator size="small" color={colors.sunset} /> : <Ionicons name="sparkles" size={14} color={colors.sunset} />}
          <Text style={[type.caption, { color: colors.inkSoft }]}>{t(coach === "thinking" ? "path.coachThinking" : "path.coachReady")}</Text>
        </Animated.View>
      )}
      {finished && (
        <Animated.View entering={ZoomIn.springify().damping(14)} style={[styles.celebrate, shadow(1)]}>
          <Ionicons name="sparkles" size={22} color={colors.sunset} />
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={type.headline}>{t("path.celebrate")}</Text>
            <Text style={type.caption}>{t("path.celebrateHint")}</Text>
          </View>
        </Animated.View>
      )}
      <View>
        {stops.map((stop, i) => {
          const now = i === current;
          const last = i === stops.length - 1;
          return (
            <Animated.View key={stop.kind} entering={FadeInDown.delay(i * 70).duration(320)} layout={SPRING} style={styles.stop}>
              <View style={styles.rail}>
                {stops.length > 1 && <View style={[styles.line, i === 0 && { top: NODE_MID }, last && { bottom: undefined, height: NODE_MID }]} />}
                <View style={[styles.node, stop.done && styles.nodeDone, now && styles.nodeNow]}>
                  <Ionicons
                    name={stop.done ? "checkmark" : STOP_ICONS[stop.kind]}
                    size={now ? 15 : 13}
                    color={stop.done || now ? "#fff" : colors.muted}
                  />
                </View>
              </View>
              {now ? (
                <Animated.View entering={FadeInDown.duration(280)} style={{ flex: 1 }}>
                  <LinearGradient colors={gradients.dusk} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={[styles.hero, shadow(3)]}>
                    <Text style={styles.heroOverline}>{t("path.now", { minutes: stop.minutes })}</Text>
                    <Text style={styles.heroTitle}>{stop.kind === "story" ? t("path.story.title") : title(stop)}</Text>
                    <Text style={styles.heroWhy}>{why(stop)}</Text>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={action(stop)}
                      accessibilityState={{ busy: busy(stop), disabled: busy(stop) }}
                      disabled={busy(stop)}
                      onPress={() => go(stop)}
                      style={({ pressed }) => [styles.heroButton, { transform: [{ scale: pressed ? 0.98 : 1 }], opacity: pressed ? 0.92 : 1 }]}
                    >
                      {busy(stop) ? <ActivityIndicator color={colors.accent} /> : <Ionicons name="play" size={18} color={colors.accent} />}
                      <Text style={styles.heroButtonText} numberOfLines={2}>
                        {action(stop)}
                      </Text>
                    </Pressable>
                    {stop.kind === "story" && storyBusy && <Text style={styles.heroWhy}>{t("city.planningHint")}</Text>}
                  </LinearGradient>
                </Animated.View>
              ) : (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={title(stop)}
                  accessibilityState={{ busy: busy(stop) }}
                  disabled={busy(stop)}
                  onPress={() => go(stop)}
                  style={({ pressed }) => [styles.row, pressed && { opacity: 0.6 }]}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={[type.callout, { color: stop.done ? colors.muted : colors.ink }]} numberOfLines={1}>
                      {title(stop)}
                    </Text>
                    <Text style={type.caption}>{stop.done ? t("path.doneToday") : t("units.minutes", { count: stop.minutes })}</Text>
                  </View>
                  {busy(stop) ? (
                    <ActivityIndicator size="small" color={colors.muted} />
                  ) : (
                    <Ionicons name={I18nManager.isRTL ? "chevron-back" : "chevron-forward"} size={16} color={colors.muted} />
                  )}
                </Pressable>
              )}
            </Animated.View>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: space(1), marginHorizontal: space(0.5) },
  coach: { flexDirection: "row", alignItems: "center", gap: 6, marginHorizontal: space(0.5), marginTop: -space(0.5) },
  stop: { flexDirection: "row", gap: space(1.25) },
  rail: { width: RAIL, alignItems: "center" },
  line: { position: "absolute", top: 0, bottom: 0, width: 2, backgroundColor: colors.border },
  node: {
    marginTop: NODE_TOP,
    width: RAIL,
    height: RAIL,
    borderRadius: RAIL / 2,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.paperDeep,
    borderWidth: 2,
    borderColor: colors.paper,
  },
  nodeDone: { backgroundColor: colors.success },
  nodeNow: { backgroundColor: colors.accent },
  row: { flex: 1, flexDirection: "row", alignItems: "center", gap: space(1), minHeight: 52, paddingVertical: space(1) },
  hero: { flex: 1, borderRadius: radius.xl, padding: space(2.25), gap: space(1), marginVertical: space(0.75) },
  heroOverline: { ...type.overline, color: "rgba(255,255,255,0.72)" },
  heroTitle: { fontFamily: fonts.display, fontSize: 22, lineHeight: 28, color: "#fff" },
  heroWhy: { fontFamily: fonts.body, fontSize: 15, lineHeight: 21, color: "rgba(255,255,255,0.88)" },
  heroButton: {
    marginTop: space(0.5),
    minHeight: 52,
    borderRadius: radius.md,
    backgroundColor: "#fff",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: space(1),
    paddingHorizontal: space(2),
  },
  heroButtonText: { fontFamily: fonts.semibold, fontSize: 16, color: colors.accentDeep, flexShrink: 1 },
  celebrate: {
    flexDirection: "row",
    alignItems: "center",
    gap: space(1.5),
    padding: space(2),
    borderRadius: radius.lg,
    backgroundColor: colors.sunsetSoft,
  },
});
