/** Exam Hall: each exam as a full mock runs it (sections in the official order and timing), placement beside it. */
import { router } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Text, View } from "react-native";

import type { CityEntry, ExamFormat, StepView } from "@/api/types";
import { useApi } from "@/state/auth";
import { useCities } from "@/state/cities";
import { useResource } from "@/state/resource";
import { Body, Button, Card, ErrorText, IconBubble, ListRow, Overline, Screen, Section, Title, type IconName } from "@/ui/kit";
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
  const formats = useResource(() => api.get<ExamFormat[]>("/v1/exams/formats"), [api]);
  const [starting, setStarting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const begin = async (key: string, path: string, body: object, language: CityEntry["language"]) => {
    setError(null);
    setStarting(key);
    try {
      const step = await api.post<StepView>(path, body);
      if (step.done) router.push("/(tabs)/passport");
      else router.push({ pathname: "/thread/[id]", params: { id: step.thread_id, first: JSON.stringify(step), language } });
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
    <Screen title={t("exam.title")} onRefresh={formats.reload}>
      <Body muted>{t("exam.intro")}</Body>
      <ErrorText message={cities.error ?? formats.error ?? error} />
      {cities.data?.map(({ language, pack, pack_name }) => {
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
                <View style={{ gap: space(1) }}>
                  <Overline>{t("exam.officialOrder")}</Overline>
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
                </View>
              )}
              <Button label={t("exam.start")} icon="timer-outline" busy={starting === `${pack}:mock`} onPress={() => void begin(`${pack}:mock`, "/v1/exams", { pack }, language)} />
            </Card>
            <Section title={t("exam.placementTitle")}>
              <ListRow
                icon="speedometer"
                title={t("exam.quick")}
                subtitle={t("exam.placement")}
                disabled={starting !== null}
                onPress={() => void begin(`${pack}:quick`, "/v1/placement", { language, path: "quick" }, language)}
              />
              <ListRow icon="play-skip-forward" title={t("exam.skip")} disabled={starting !== null} onPress={() => void begin(`${pack}:skip`, "/v1/placement", { language, path: "skip" }, language)} />
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
