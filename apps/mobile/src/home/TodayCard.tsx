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

export function TodayCard({ today, onStartStory }: { today: Today; onStartStory: () => void }) {
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
  return (
    <Card>
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
                  {t(`skills.${s.skill}`)} {levelRange(s.level_low, s.level_high)}/{s.target}
                </Text>
              </View>
            ))}
          </View>
        </View>
      ))}
      {today.reviews_due > 0 && <Body muted>{t("today.reviewsDue", { count: today.reviews_due })}</Body>}
      {today.lessons_waiting > 0 && <Body muted>{t("today.lessonsWaiting", { count: today.lessons_waiting })}</Body>}
      <Button label={t(`today.next.${today.next_step}`)} onPress={go} />
    </Card>
  );
}
