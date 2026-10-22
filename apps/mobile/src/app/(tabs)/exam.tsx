/** Exam Hall: each exam as a full mock runs it (sections in the official order and timing), placement beside it. */
import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { Text, View } from "react-native";

import type { CityEntry, ExamFormat, StepView, Today } from "@/api/types";
import { useApi } from "@/state/auth";
import { useCities } from "@/state/cities";
import { useFocus } from "@/state/focus";
import { useResource } from "@/state/resource";
import { Body, Button, Card, Disclosure, ErrorText, IconBubble, ListRow, Overline, Screen, Section, Title, type IconName } from "@/ui/kit";
import { FocusSwitch } from "@/ui/FocusSwitch";
import { space, type } from "@/ui/theme";

const SKILL_ICONS: Record<ExamFormat["sections"][number]["skill"], IconName> = {
  reading: "book",
  listening: "headset",
  writing: "create",
  speaking: "mic",
};

export default function ExamHall() {
  const { t } = useTranslation();
  const api = useApi();
  const cities = useCities();
  const focus = useFocus();
  const formats = useResource(() => api.get<ExamFormat[]>("/v1/exams/formats"), [api]);
  const today = useResource(() => api.get<Today>("/v1/today"), [api]);
  const { reload: reloadToday } = today;
  useFocusEffect(useCallback(() => reloadToday(), [reloadToday]));
  // During onboarding the hall opens on the one thing asked of the learner here: find a level, or skip it.
  const placing = today.data?.onboarding.goal === true && !today.data.onboarding.placement;
  const studying = new Set(today.data?.goals.map((g) => g.pack));
  const [starting, setStarting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const begin = async (key: string, path: string, body: object, language: CityEntry["language"]) => {
    setError(null);
    setStarting(key);
    try {
      const step = await api.post<StepView>(path, body);
      // A placement ends at Home, where the next step of the journey waits; a mock ends at its scores in the Passport.
      const then = key.endsWith(":mock") ? "passport" : "home";
      if (step.done) router.navigate(then === "home" ? "/(tabs)/city" : "/(tabs)/passport");
      else router.push({ pathname: "/thread/[id]", params: { id: step.thread_id, first: JSON.stringify(step), language, then } });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(null);
    }
  };

  const duration = (minutes: number) => t("exam.duration", { h: Math.floor(minutes / 60), m: String(minutes % 60).padStart(2, "0") });
  const amount = (s: ExamFormat["sections"][number]) =>
    s.questions !== null
      ? t("exam.questionsN", { count: s.questions })
      : s.skill === "writing"
        ? t("exam.tasksN", { count: s.tasks })
        : t("exam.partsN", { count: s.tasks });

  return (
    <Screen title={t("exam.title")} accessory={placing ? undefined : <FocusSwitch />} onRefresh={formats.reload}>
      {placing ? (
        <Card tone="accent" style={{ gap: space(1.5) }}>
          <Overline>{t("onboarding.stepOf", { step: 2, total: 3 })}</Overline>
          <Title>{t("onboarding.placementTitle")}</Title>
          <Body>{t("onboarding.placementBody")}</Body>
          {cities.data
            ?.filter((c) => studying.size === 0 || studying.has(c.pack))
            .map(({ language, pack, pack_name }) => (
              <Section key={pack} title={pack_name}>
                <ListRow
                  icon="speedometer"
                  title={t("exam.quick")}
                  subtitle={t("exam.placement")}
                  disabled={starting !== null}
                  onPress={() => void begin(`${pack}:quick`, "/v1/placement", { language, path: "quick" }, language)}
                />
                <ListRow
                  icon="play-skip-forward"
                  title={t("exam.skip")}
                  subtitle={t("onboarding.skipHint")}
                  disabled={starting !== null}
                  onPress={() => void begin(`${pack}:skip`, "/v1/placement", { language, path: "skip" }, language)}
                />
              </Section>
            ))}
          <Button label={t("onboarding.backHome")} kind="ghost" icon="home" onPress={() => router.navigate("/(tabs)/city")} />
        </Card>
      ) : null}
      <ErrorText message={cities.error ?? formats.error ?? error} />
      {cities.data?.filter((c) => c.language === focus.language).map(({ language, pack, pack_name }) => {
        const format = formats.data?.find((f) => f.pack === pack);
        return (
          <View key={language} style={{ gap: space(1.5) }}>
            <Card style={{ gap: space(2) }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: space(1.5) }}>
                <IconBubble name="ribbon" tone="accent" size={48} />
                <View style={{ flex: 1, gap: 2 }}>
                  <Title>{pack_name}</Title>
                  {format && <Text style={type.caption}>{t("exam.fullMock", { time: duration(format.total_minutes) })}</Text>}
                </View>
              </View>
              {format && (
                // The parts in their official order and timing, folded: the mock runs them for the learner anyway.
                <Disclosure title={t("exam.officialOrder")} hint={t("exam.partsN", { count: format.sections.length })}>
                  {format.sections.map((s, i) => (
                    <View key={s.id} style={{ flexDirection: "row", alignItems: "center", gap: space(1.25) }}>
                      <Text style={[type.caption, { width: 16 }]}>{i + 1}</Text>
                      <IconBubble name={SKILL_ICONS[s.skill]} size={32} />
                      <Text style={[type.headline, { flex: 1 }]}>{t(`exam.sections.${s.id}`)}</Text>
                      <Text style={type.caption}>
                        {t("units.minutes", { count: s.minutes })} · {amount(s)}
                      </Text>
                    </View>
                  ))}
                </Disclosure>
              )}
              <Button label={t("exam.start")} icon="timer-outline" busy={starting === `${pack}:mock`} onPress={() => void begin(`${pack}:mock`, "/v1/exams", { pack }, language)} />
            </Card>
            <Section>
              <ListRow
                icon="speedometer"
                title={t("exam.recheck")}
                subtitle={t("exam.placement")}
                disabled={starting !== null}
                onPress={() => void begin(`${pack}:quick`, "/v1/placement", { language, path: "quick" }, language)}
              />
            </Section>
          </View>
        );
      })}
      <Section>
        <ListRow icon="create" title={t("exam.desk")} subtitle={t("exam.deskHint")} onPress={() => router.push("/desk")} />
      </Section>
    </Screen>
  );
}
