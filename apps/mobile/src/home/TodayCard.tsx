/** Home card: streak, exam countdowns, the gap to the learner's goal, and the one thing to do next. */
import { router } from "expo-router";
import { useTranslation } from "react-i18next";
import { Text, View } from "react-native";

import type { SkillStatus, Today } from "@/api/types";
import { levelRange } from "@/home/levels";
import { Body, Button, Card, Title } from "@/ui/kit";
import { colors } from "@/ui/theme";

const STATUS_COLOUR: Record<SkillStatus, string> = {
  met: colors.success,
  close: "#b7791f",
  behind: colors.danger,
  unknown: colors.muted,
};

// Level ranges sit in a left-to-right isolate (U+2066…U+2069) so "<4–8/7" reads the same inside Arabic text.
export function TodayCard({ today, onStartStory, busy = false }: { today: Today; onStartStory: () => void; busy?: boolean }) {
  const { t } = useTranslation();
  const go = () => {
    switch (today.next_step) {
      case "set_goal":
        return router.push("/goal");
      case "placement":
        return router.push("/(tabs)/exam");
      case "reviews":
        return router.push("/(tabs)/phone");
      case "lesson":
        return router.push("/(tabs)/school");
      default:
        return onStartStory();
    }
  };
  const steps = [
    { done: today.onboarding.goal, label: t("onboarding.goal") },
    { done: today.onboarding.placement, label: t("onboarding.placement") },
    { done: today.onboarding.first_story, label: t("onboarding.firstStory") },
  ];
  const onboarding = steps.some((s) => !s.done);
  return (
    <Card>
      {onboarding && (
        <View style={{ gap: 4 }} accessible accessibilityLabel={t("onboarding.title")}>
          <Title>{t("onboarding.title")}</Title>
          {steps.map((s, i) => (
            <Text key={s.label} style={{ fontSize: 16, color: s.done ? colors.success : colors.ink }}>
              {s.done ? "✓" : `${i + 1}.`} {s.label}
            </Text>
          ))}
        </View>
      )}
      <Title>{today.streak > 0 ? `🔥 ${t("today.streak", { count: today.streak })}` : t("today.noStreak")}</Title>
      {today.practised_today && <Body muted>{t("today.practised")}</Body>}
      {today.goals.map((goal) => (
        <View key={goal.pack} style={{ gap: 4 }}>
          <Body>
            {goal.days_left === null
              ? t("today.noDate", { exam: goal.pack_name })
              : goal.days_left < 0
                ? t("today.examPast", { exam: goal.pack_name })
                : t("today.examIn", { exam: goal.pack_name, count: goal.days_left })}
          </Body>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
            {goal.skills.map((s) => (
              <View
                key={s.skill}
                accessible
                accessibilityLabel={`${t(`skills.${s.skill}`)}: ${levelRange(s.level_low, s.level_high)} / ${s.target}, ${t(`today.status.${s.status}`)}`}
                style={{ borderRadius: 999, borderWidth: 1, borderColor: STATUS_COLOUR[s.status], paddingHorizontal: 10, paddingVertical: 4 }}
              >
                <Text style={{ color: STATUS_COLOUR[s.status], fontSize: 13 }}>
                  {t(`skills.${s.skill}`)} {"\u2066"}{levelRange(s.level_low, s.level_high)}/{s.target}{"\u2069"}
                </Text>
              </View>
            ))}
          </View>
        </View>
      ))}
      {today.reviews_due > 0 && <Body muted>{t("today.reviewsDue", { count: today.reviews_due })}</Body>}
      {today.lessons_waiting > 0 && <Body muted>{t("today.lessonsWaiting", { count: today.lessons_waiting })}</Body>}
      <Button label={busy ? t("city.planning") : t(`today.next.${today.next_step}`)} busy={busy} onPress={go} />
      {busy && <Body muted>{t("city.planningHint")}</Body>}
    </Card>
  );
}
