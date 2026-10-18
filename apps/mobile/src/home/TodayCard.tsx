/** Home hero: the one thing to do next, with the streak, exam countdowns and the gap to the learner's goal.
 * While the learner is new, a short checklist above it shows where they are in getting started. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { LinearGradient } from "expo-linear-gradient";
import { router } from "expo-router";
import { useTranslation } from "react-i18next";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import type { SkillStatus, Today } from "@/api/types";
import { levelProgress, levelRange } from "@/home/levels";
import { Card, ProgressBar } from "@/ui/kit";
import { colors, fonts, gradients, radius, shadow, space, type } from "@/ui/theme";

const STATUS_DOT: Record<SkillStatus, string> = {
  met: "#7FE0A8",
  close: "#FFD38A",
  behind: "#FFA594",
  unknown: "rgba(255,255,255,0.45)",
};

function Onboarding({ today }: { today: Today }) {
  const { t } = useTranslation();
  const steps = [
    { done: today.onboarding.goal, label: t("onboarding.goal") },
    { done: today.onboarding.placement, label: t("onboarding.placement") },
    { done: today.onboarding.first_story, label: t("onboarding.firstStory") },
  ];
  const done = steps.filter((s) => s.done).length;
  if (done === steps.length) return null;
  const current = steps.findIndex((s) => !s.done);
  return (
    <Card>
      <View style={styles.rowBetween}>
        <Text style={type.headline}>{t("onboarding.title")}</Text>
        <Text style={type.caption}>{t("onboarding.progress", { done, total: steps.length })}</Text>
      </View>
      <ProgressBar value={done / steps.length} tone="success" />
      <View style={{ gap: space(1.25), marginTop: space(0.5) }} accessible accessibilityLabel={t("onboarding.title")}>
        {steps.map((s, i) => (
          <View key={s.label} style={styles.step}>
            {s.done ? (
              <Ionicons name="checkmark-circle" size={22} color={colors.success} />
            ) : (
              <View style={[styles.stepNumber, i === current && styles.stepNumberCurrent]}>
                <Text style={[type.caption, { color: i === current ? colors.accentInk : colors.muted, fontFamily: fonts.semibold }]}>{i + 1}</Text>
              </View>
            )}
            <Text
              style={[
                type.callout,
                { flex: 1, color: s.done ? colors.muted : colors.ink },
                s.done && { textDecorationLine: "line-through" },
                i === current && { fontFamily: fonts.semibold },
              ]}
            >
              {s.label}
            </Text>
          </View>
        ))}
      </View>
    </Card>
  );
}

// Level ranges sit in a left-to-right isolate (U+2066…U+2069) so "<4–8/7" reads the same inside Arabic text.
/** ``day``: the story day to play next in the chosen city (progress, not the calendar); null while loading. */
export function TodayCard({
  today,
  day,
  scales,
  onStartStory,
  busy = false,
}: {
  today: Today;
  day: number | null;
  /** The level scale of each exam pack (NCLC, CLB), to explain the levels in plain words. */
  scales: Record<string, string>;
  onStartStory: () => void;
  busy?: boolean;
}) {
  const { t } = useTranslation();
  const go = () => {
    switch (today.next_step) {
      case "set_goal":
        return router.push("/goal");
      case "placement":
        return router.push("/(tabs)/exam");
      case "lesson":
        return router.push("/(tabs)/school");
      default:
        return onStartStory();
    }
  };
  const action = busy
    ? t("city.planning")
    : today.next_step === "story"
      ? day
        ? t("today.next.story", { day })
        : t("city.startDay")
      : t(`today.next.${today.next_step}`);
  return (
    <View style={{ gap: space(2) }}>
      <Onboarding today={today} />
      <LinearGradient colors={gradients.dusk} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={[styles.hero, shadow(3)]}>
        <Text style={styles.heroOverline}>{t("today.nextUp")}</Text>
        <View style={styles.streakRow}>
          <Ionicons name={today.streak > 0 ? "flame" : "flame-outline"} size={28} color="#FFB37D" />
          <Text style={styles.heroTitle} accessibilityRole="header">
            {today.streak > 0 ? t("today.streak", { count: today.streak }) : t("today.noStreak")}
          </Text>
        </View>
        {today.goals.map((goal) => (
          <View key={goal.pack} style={{ gap: space(1) }}>
            <Text style={styles.heroBody}>
              {goal.days_left === null
                ? t("today.noDate", { exam: goal.pack_name })
                : goal.days_left < 0
                  ? t("today.examPast", { exam: goal.pack_name })
                  : t("today.examIn", { exam: goal.pack_name, count: goal.days_left })}
            </Text>
            <View style={{ gap: space(1.5) }}>
              {goal.skills.map((s) => (
                <View
                  key={s.skill}
                  style={styles.skill}
                  accessible
                  accessibilityLabel={`${t(`skills.${s.skill}`)}: ${levelRange(s.level_low, s.level_high)} / ${s.target}, ${t(`today.status.${s.status}`)}`}
                >
                  <View style={styles.skillHead}>
                    <Text style={styles.skillName}>{t(`skills.${s.skill}`)}</Text>
                    <Text style={styles.skillStatus}>
                      {t(`today.status.${s.status}`)} · {t("today.goalLevel", { level: s.target })}
                    </Text>
                  </View>
                  <View style={styles.skillTrack}>
                    <View
                      style={[styles.skillFill, { width: `${levelProgress(s.level_low, s.level_high, s.target) * 100}%`, backgroundColor: STATUS_DOT[s.status] }]}
                    />
                  </View>
                </View>
              ))}
            </View>
            {scales[goal.pack] && <Text style={styles.heroHint}>{t("today.levelsHint", { scale: scales[goal.pack] })}</Text>}
          </View>
        ))}
        {today.lessons_waiting > 0 && today.next_step !== "lesson" && (
          <Text style={styles.heroNote}>• {t("today.lessonsWaiting", { count: today.lessons_waiting })}</Text>
        )}
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={action}
          accessibilityState={{ busy, disabled: busy }}
          disabled={busy}
          onPress={go}
          style={({ pressed }) => [styles.heroButton, { transform: [{ scale: pressed ? 0.98 : 1 }], opacity: pressed ? 0.92 : 1 }]}
        >
          {busy ? <ActivityIndicator color={colors.accent} /> : <Ionicons name="play" size={18} color={colors.accent} />}
          <Text style={styles.heroButtonText} numberOfLines={1}>
            {action}
          </Text>
        </Pressable>
        {busy && <Text style={[styles.heroNote, { textAlign: "center" }]}>{t("city.planningHint")}</Text>}
        {today.reviews_due > 0 && (
          // Reviews follow their own spaced schedule; they sit beside the story and never stand in its way.
          <Pressable
            accessibilityRole="button"
            onPress={() => router.push("/(tabs)/phone")}
            style={({ pressed }) => [styles.sideAction, pressed && { opacity: 0.7 }]}
          >
            <Ionicons name="flash" size={15} color="#fff" />
            <Text style={styles.sideActionText} numberOfLines={1}>
              {t("today.reviewsAction", { count: today.reviews_due })}
            </Text>
            <Ionicons name="chevron-forward" size={15} color="rgba(255,255,255,0.8)" />
          </Pressable>
        )}
      </LinearGradient>
    </View>
  );
}

const styles = StyleSheet.create({
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: space(1) },
  step: { flexDirection: "row", alignItems: "center", gap: space(1.25) },
  stepNumber: { width: 22, height: 22, borderRadius: 11, borderWidth: 1.5, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  stepNumberCurrent: { backgroundColor: colors.accent, borderColor: colors.accent },
  hero: { borderRadius: radius.xl, padding: space(3), gap: space(1.5) },
  heroOverline: { ...type.overline, color: "rgba(255,255,255,0.72)" },
  streakRow: { flexDirection: "row", alignItems: "center", gap: space(1) },
  heroTitle: { fontFamily: fonts.displayBold, fontSize: 28, lineHeight: 34, color: "#fff", flexShrink: 1 },
  heroBody: { fontFamily: fonts.medium, fontSize: 15, lineHeight: 21, color: "rgba(255,255,255,0.88)" },
  heroNote: { fontFamily: fonts.medium, fontSize: 13, color: "rgba(255,255,255,0.8)" },
  skills: { flexDirection: "row", flexWrap: "wrap", gap: space(1) },
  skill: { gap: 6 },
  skillHead: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", columnGap: space(1) },
  skillName: { fontFamily: fonts.semibold, fontSize: 14, color: "#fff" },
  skillTrack: { height: 6, borderRadius: 3, backgroundColor: "rgba(255,255,255,0.18)", overflow: "hidden" },
  skillFill: { height: "100%", borderRadius: 3 },
  skillStatus: { fontFamily: fonts.medium, fontSize: 13, color: "rgba(255,255,255,0.85)", flexShrink: 1, textAlign: "right" },
  heroHint: { fontFamily: fonts.body, fontSize: 12, lineHeight: 17, color: "rgba(255,255,255,0.7)" },
  sideAction: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, minHeight: 40 },
  sideActionText: { fontFamily: fonts.semibold, fontSize: 14, color: "#fff", flexShrink: 1 },
  heroButton: {
    marginTop: space(0.5),
    minHeight: 54,
    borderRadius: radius.md,
    backgroundColor: "#fff",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: space(1),
    paddingHorizontal: space(2),
  },
  heroButtonText: { fontFamily: fonts.semibold, fontSize: 16, color: colors.accentDeep, flexShrink: 1 },
});
