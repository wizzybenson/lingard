import { router } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { CityEntry, StepView } from "@/api/types";
import { useApi } from "@/state/auth";
import { useCities } from "@/state/cities";
import { View } from "react-native";

import { Body, Button, Card, ErrorText, IconBubble, ListRow, Screen, Section, Title } from "@/ui/kit";
import { space } from "@/ui/theme";

export default function ExamHall() {
  const { t } = useTranslation();
  const api = useApi();
  const cities = useCities();
  const [error, setError] = useState<string | null>(null);

  const begin = async (path: string, body: object, language: CityEntry["language"]) => {
    setError(null);
    try {
      const step = await api.post<StepView>(path, body);
      if (step.done) router.push("/(tabs)/passport");
      else router.push({ pathname: "/thread/[id]", params: { id: step.thread_id, first: JSON.stringify(step), language } });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <Screen title={t("exam.title")}>
      <Body muted>{t("exam.intro")}</Body>
      <ErrorText message={cities.error ?? error} />
      {cities.data?.map(({ language, pack, pack_name }) => (
        <Card key={language}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: space(1.5) }}>
            <IconBubble name="ribbon" tone="accent" size={44} />
            <View style={{ flex: 1 }}>
              <Title>{pack_name}</Title>
              <Body muted>{t("exam.placement")}</Body>
            </View>
          </View>
          <Button label={t("exam.quick")} icon="speedometer" onPress={() => void begin("/v1/placement", { language, path: "quick" }, language)} />
          <Button label={t("exam.start")} kind="secondary" icon="timer-outline" onPress={() => void begin("/v1/exams", { pack }, language)} />
          <Button label={t("exam.skip")} kind="ghost" onPress={() => void begin("/v1/placement", { language, path: "skip" }, language)} />
        </Card>
      ))}
      <Section>
        <ListRow icon="create" title={t("exam.desk")} subtitle={t("exam.deskHint")} onPress={() => router.push("/desk")} />
      </Section>
    </Screen>
  );
}
