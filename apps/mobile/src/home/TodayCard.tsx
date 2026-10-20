/** Home hero: the one thing to do next and the streak, kept short; under it a slim strip of exam countdowns and the
 * gap to the goal per skill. While the learner is new, a short checklist above it shows where they are in getting
 * started. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { LinearGradient } from "expo-linear-gradient";
import { router } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ActivityIndicator,
  I18nManager,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import type { SkillStatus, Today } from "@/api/types";
import { levelProgress, levelRange } from "@/home/levels";
import { openKeyPoint } from "@/school/keyPoints";
import { useApi } from "@/state/auth";
import { Card, ProgressBar } from "@/ui/kit";
import {
  colors,
  fonts,
  gradients,
  radius,
  shadow,
  space,
  type,
} from "@/ui/theme";

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
        <Text style={type.caption}>
          {t("onboarding.progress", { done, total: steps.length })}
        </Text>
      </View>
      <ProgressBar value={done / steps.length} tone="success" />
      <View
        style={{ gap: space(1.25), marginTop: space(0.5) }}
        accessible
        accessibilityLabel={t("onboarding.title")}
      >
        {steps.map((s, i) => (
          <View key={s.label} style={styles.step}>
            {s.done ? (
              <Ionicons
                name="checkmark-circle"
                size={22}
                color={colors.success}
              />
            ) : (
              <View
                style={[
                  styles.stepNumber,
                  i === current && styles.stepNumberCurrent,
                ]}
              >
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

/** ``day``: the story day to play next in the chosen city (progress, not the calendar); null while loading. */
export function TodayCard({
  today,
  day,
  onStartStory,
  busy = false,
}: {
  today: Today;
  day: number | null;
  onStartStory: () => void;
  busy?: boolean;
}) {
  const { t } = useTranslation();
  const api = useApi();
  const [opening, setOpening] = useState(false);
  const go = () => {
    switch (today.next_step) {
      case "key_points":
        if (!today.next_key_point) return router.push("/(tabs)/school");
        setOpening(true);
        return void openKeyPoint(api, today.next_key_point.node_key)
          .catch(() => router.push("/(tabs)/school"))
          .finally(() => setOpening(false));
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
  const working = busy || opening;
  const action = busy
    ? t("city.planning")
    : today.next_step === "key_points" && today.next_key_point
      ? t("today.next.key_points", { title: today.next_key_point.title })
      : today.next_step === "story"
        ? day
          ? t("today.next.story", { day })
          : t("city.startDay")
        : t(`today.next.${today.next_step}`);
  return (
    <View style={{ gap: space(1.5) }}>
      <Onboarding today={today} />
      <LinearGradient
        colors={gradients.dusk}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={[styles.hero, shadow(3)]}
      >
        <View style={styles.rowBetween}>
          <Text style={styles.heroOverline}>{t("today.nextUp")}</Text>
          <View
            style={{ flexDirection: "row", gap: space(0.75), flexShrink: 1 }}
          >
            <View
              style={styles.streak}
              accessible
              accessibilityLabel={
                today.streak > 0
                  ? t("today.streak", { count: today.streak })
                  : t("today.noStreak")
              }
            >
              <Ionicons
                name={today.streak > 0 ? "flame" : "flame-outline"}
                size={16}
                color="#FFB37D"
              />
              <Text style={styles.streakText} numberOfLines={1}>
                {today.streak > 0
                  ? t("today.streak", { count: today.streak })
                  : t("today.noStreak")}
              </Text>
              {today.freezes > 0 && (
                <View
                  style={styles.freezes}
                  accessible
                  accessibilityLabel={t("shop.freezesHeld", {
                    count: today.freezes,
                  })}
                >
                  <Ionicons name="snow" size={13} color="#BFE3FF" />
                  <Text style={styles.streakText}>{today.freezes}</Text>
                </View>
              )}
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={t("wallet.coinsCount", {
                count: today.coins,
              })}
              onPress={() => router.push("/shop")}
              style={styles.streak}
            >
              <Ionicons name="cash" size={16} color="#FFD38A" />
              <Text style={styles.streakText}>{today.coins}</Text>
            </Pressable>
          </View>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={action}
          accessibilityState={{ busy: working, disabled: working }}
          disabled={working}
          onPress={go}
          style={({ pressed }) => [
            styles.heroButton,
            {
              transform: [{ scale: pressed ? 0.98 : 1 }],
              opacity: pressed ? 0.92 : 1,
            },
          ]}
        >
          {working ? (
            <ActivityIndicator color={colors.accent} />
          ) : (
            <Ionicons name="play" size={18} color={colors.accent} />
          )}
          <Text style={styles.heroButtonText} numberOfLines={2}>
            {action}
          </Text>
        </Pressable>
        {busy && (
          <Text style={[styles.heroNote, { textAlign: "center" }]}>
            {t("city.planningHint")}
          </Text>
        )}
        {(today.reviews_due > 0 ||
          (today.lessons_waiting > 0 && today.next_step !== "lesson")) && (
          // Reviews and waiting lessons sit beside the story and never stand in its way.
          <View style={styles.extras}>
            {today.reviews_due > 0 && (
              <Pressable
                accessibilityRole="button"
                onPress={() => router.push("/(tabs)/phone")}
                style={({ pressed }) => [
                  styles.extra,
                  pressed && { opacity: 0.7 },
                ]}
              >
                <Ionicons name="flash" size={14} color="#fff" />
                <Text style={styles.extraText} numberOfLines={1}>
                  {t("today.reviewsAction", { count: today.reviews_due })}
                </Text>
              </Pressable>
            )}
            {today.lessons_waiting > 0 && today.next_step !== "lesson" && (
              <Pressable
                accessibilityRole="button"
                onPress={() => router.push("/(tabs)/school")}
                style={({ pressed }) => [
                  styles.extra,
                  pressed && { opacity: 0.7 },
                ]}
              >
                <Ionicons name="school" size={14} color="#fff" />
                <Text style={styles.extraText} numberOfLines={1}>
                  {t("today.lessonsWaiting", { count: today.lessons_waiting })}
                </Text>
              </Pressable>
            )}
          </View>
        )}
      </LinearGradient>
      {today.goals.length > 0 && <ExamProgress today={today} />}
    </View>
  );
}

/** One slim line per exam: the countdown and a small bar per skill, coloured by how close it is to the goal.
 * The full picture (levels, targets, what the scale means) is one tap away in the Passport. */
function ExamProgress({ today }: { today: Today }) {
  const { t } = useTranslation();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityHint={t("today.examDetails")}
      onPress={() => router.push("/(tabs)/passport")}
      style={({ pressed }) => [
        styles.exams,
        shadow(1),
        pressed && { opacity: 0.85 },
      ]}
    >
      {today.goals.map((goal, i) => (
        <View
          key={goal.pack}
          style={[{ gap: space(1) }, i > 0 && styles.examDivider]}
        >
          <View style={styles.rowBetween}>
            <Text style={[type.headline, { flexShrink: 1 }]} numberOfLines={1}>
              {goal.pack_name}
            </Text>
            <Text style={type.caption}>
              {goal.days_left === null
                ? t("today.noDateShort")
                : goal.days_left < 0
                  ? t("today.pastShort")
                  : t("today.daysLeft", { count: goal.days_left })}
            </Text>
          </View>
          <View style={styles.skills}>
            {goal.skills.map((s) => (
              <View
                key={s.skill}
                style={styles.skill}
                accessible
                accessibilityLabel={`${t(`skills.${s.skill}`)}: ${levelRange(s.level_low, s.level_high)} / ${s.target}, ${t(`today.status.${s.status}`)}`}
              >
                <Text style={styles.skillName} numberOfLines={1}>
                  {t(`skills.${s.skill}`)}
                </Text>
                <View style={styles.skillTrack}>
                  <View
                    style={[
                      styles.skillFill,
                      {
                        width: `${Math.max(levelProgress(s.level_low, s.level_high, s.target), 0.04) * 100}%`,
                        backgroundColor: STATUS_COLOR[s.status],
                      },
                    ]}
                  />
                </View>
              </View>
            ))}
          </View>
        </View>
      ))}
      <View style={styles.legend}>
        {(["met", "close", "behind"] as const).map((status) => (
          <View key={status} style={styles.legendItem}>
            <View
              style={[
                styles.legendDot,
                { backgroundColor: STATUS_COLOR[status] },
              ]}
            />
            <Text style={type.caption}>{t(`today.status.${status}`)}</Text>
          </View>
        ))}
        <View style={{ flex: 1 }} />
        <Ionicons
          name={I18nManager.isRTL ? "chevron-back" : "chevron-forward"}
          size={16}
          color={colors.muted}
        />
      </View>
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
  streak: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: "rgba(255,255,255,0.14)",
    borderRadius: radius.pill,
    paddingHorizontal: space(1.25),
    paddingVertical: 4,
  },
  freezes: {
    flexDirection: "row",
    alignItems: "center",
    gap: 2,
    marginStart: space(0.5),
  },
  streakText: { fontFamily: fonts.semibold, fontSize: 13, color: "#fff" },
  heroNote: {
    fontFamily: fonts.medium,
    fontSize: 13,
    color: "rgba(255,255,255,0.8)",
  },
  extras: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "center",
    gap: space(1),
  },
  extra: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    minHeight: 36,
    paddingHorizontal: space(1.25),
    borderRadius: radius.pill,
    backgroundColor: "rgba(255,255,255,0.14)",
  },
  extraText: {
    fontFamily: fonts.semibold,
    fontSize: 13,
    color: "#fff",
    flexShrink: 1,
  },
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
  heroButtonText: {
    fontFamily: fonts.semibold,
    fontSize: 16,
    color: colors.accentDeep,
    flexShrink: 1,
  },
  exams: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    padding: space(2),
    gap: space(1.5),
  },
  examDivider: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    paddingTop: space(1.5),
  },
  skills: { flexDirection: "row", gap: space(1) },
  skill: { flex: 1, gap: 5, minWidth: 0 },
  skillName: { fontFamily: fonts.medium, fontSize: 12, color: colors.inkSoft },
  skillTrack: {
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.paper,
    overflow: "hidden",
  },
  skillFill: { height: "100%", borderRadius: 3 },
  legend: { flexDirection: "row", alignItems: "center", gap: space(1.5) },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 5 },
  legendDot: { width: 8, height: 8, borderRadius: 4 },
});
