/** Home pieces around today's path: while the learner is new, a short checklist and the one step to take (goal, then
 * placement), since the path only starts once the level is known; the streak and coins as two quiet pills by the
 * greeting; and one line for the exam being prepared (decision 0029). */
import Ionicons from "@expo/vector-icons/Ionicons";
import { LinearGradient } from "expo-linear-gradient";
import { router } from "expo-router";
import { useTranslation } from "react-i18next";
import { I18nManager, Pressable, StyleSheet, Text, View } from "react-native";

import type { SkillStatus, Today } from "@/api/types";
import { Card, ProgressBar } from "@/ui/kit";
import { colors, fonts, gradients, radius, shadow, space, type } from "@/ui/theme";

const STATUS_COLOR: Record<SkillStatus, string> = {
  met: colors.success,
  close: colors.warning,
  behind: colors.danger,
  unknown: colors.border,
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
                <Text
                  style={[
                    type.caption,
                    {
                      color: i === current ? colors.accentInk : colors.muted,
                      fontFamily: fonts.semibold,
                    },
                  ]}
                >
                  {i + 1}
                </Text>
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

/** Before the path: the getting-started checklist and the one step it asks for now (set a goal, find a level). */
export function TodayCard({ today }: { today: Today }) {
  const { t } = useTranslation();
  const go = () => (today.next_step === "set_goal" ? router.push("/goal") : router.push("/(tabs)/exam"));
  const action = t(`today.next.${today.next_step}`);
  return (
    <View style={{ gap: space(1.5) }}>
      <Onboarding today={today} />
      <LinearGradient colors={gradients.dusk} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={[styles.hero, shadow(3)]}>
        <Text style={styles.heroOverline}>{t("today.nextUp")}</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={action}
          onPress={go}
          style={({ pressed }) => [styles.heroButton, { transform: [{ scale: pressed ? 0.98 : 1 }], opacity: pressed ? 0.92 : 1 }]}
        >
          <Ionicons name="play" size={18} color={colors.accent} />
          <Text style={styles.heroButtonText} numberOfLines={2}>
            {action}
          </Text>
        </Pressable>
      </LinearGradient>
    </View>
  );
}

/** The streak and the coins, small, beside the greeting: felt on every visit without taking the stage. */
export function Stats({ today }: { today: Today }) {
  const { t } = useTranslation();
  return (
    <View style={{ flexDirection: "row", gap: space(0.75) }}>
      <View style={styles.stat} accessible accessibilityLabel={today.streak > 0 ? t("today.streak", { count: today.streak }) : t("today.noStreak")}>
        <Ionicons name={today.streak > 0 ? "flame" : "flame-outline"} size={15} color={colors.sunset} />
        <Text style={styles.statText}>{today.streak}</Text>
        {today.freezes > 0 && <Ionicons name="snow" size={12} color={colors.accent} accessibilityLabel={t("shop.freezesHeld", { count: today.freezes })} />}
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t("wallet.coinsCount", { count: today.coins })}
        onPress={() => router.push("/shop")}
        style={({ pressed }) => [styles.stat, pressed && { opacity: 0.7 }]}
      >
        <Ionicons name="cash" size={15} color={colors.warning} />
        <Text style={styles.statText}>{today.coins}</Text>
      </Pressable>
    </View>
  );
}

/** One line for the exam in focus: the countdown and the skill furthest from the goal. Levels, targets and what the
 * scale means are one tap away in the Passport. */
export function ExamLine({ today, pack }: { today: Today; pack: string | null }) {
  const { t } = useTranslation();
  const goal = today.goals.find((g) => g.pack === pack) ?? today.goals[0];
  if (!goal) return null;
  const order = { behind: 0, close: 1, unknown: 2, met: 3 } as const;
  const weakest = [...goal.skills].sort((a, b) => order[a.status] - order[b.status])[0];
  const when = goal.days_left === null ? t("today.noDateShort") : goal.days_left < 0 ? t("today.pastShort") : t("today.daysLeft", { count: goal.days_left });
  const focusLine =
    !weakest || weakest.status === "unknown"
      ? t("today.examNotMeasured")
      : weakest.status === "met"
        ? t("today.examAllMet")
        : t("today.examWeakest", { skill: t(`skills.${weakest.skill}`) });
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityHint={t("today.examDetails")}
      onPress={() => router.push("/(tabs)/passport")}
      style={({ pressed }) => [styles.exam, shadow(1), pressed && { opacity: 0.85 }]}
    >
      <View style={[styles.dot, { backgroundColor: STATUS_COLOR[weakest?.status ?? "unknown"] }]} />
      <View style={{ flex: 1 }}>
        <Text style={type.headline} numberOfLines={1}>{`${goal.pack_name} · ${when}`}</Text>
        <Text style={type.caption} numberOfLines={1}>
          {focusLine}
        </Text>
      </View>
      <Ionicons name={I18nManager.isRTL ? "chevron-back" : "chevron-forward"} size={16} color={colors.muted} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  rowBetween: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: space(1),
  },
  step: { flexDirection: "row", alignItems: "center", gap: space(1.25) },
  stepNumber: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 1.5,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  stepNumberCurrent: {
    backgroundColor: colors.accent,
    borderColor: colors.accent,
  },
  hero: { borderRadius: radius.xl, padding: space(2.25), gap: space(1.5) },
  heroOverline: { ...type.overline, color: "rgba(255,255,255,0.72)" },
  heroButton: {
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
  stat: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    minHeight: 30,
    backgroundColor: colors.card,
    borderRadius: radius.pill,
    paddingHorizontal: space(1.25),
    ...shadow(1),
  },
  statText: { fontFamily: fonts.semibold, fontSize: 13, color: colors.ink },
  exam: {
    flexDirection: "row",
    alignItems: "center",
    gap: space(1.5),
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    paddingHorizontal: space(2),
    paddingVertical: space(1.5),
  },
  dot: { width: 10, height: 10, borderRadius: 5 },
});
