import { router } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { CityEntry, StepView } from "@/api/types";
import { useApi } from "@/state/auth";
import { useCities } from "@/state/cities";
import { Body, Button, Card, ErrorText, Screen, Title } from "@/ui/kit";

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
    <Screen>
      <Title>{t("exam.title")}</Title>
      <ErrorText message={cities.error ?? error} />
      {cities.data?.map(({ language, pack, pack_name }) => (
        <Card key={language}>
          <Title>{pack_name}</Title>
          <Body muted>{t("exam.placement")}</Body>
          <Button label={t("exam.quick")} onPress={() => void begin("/v1/placement", { language, path: "quick" }, language)} />
          <Button label={t("exam.skip")} kind="secondary" onPress={() => void begin("/v1/placement", { language, path: "skip" }, language)} />
          <Button label={t("exam.start")} kind="secondary" onPress={() => void begin("/v1/exams", { pack }, language)} />
        </Card>
      ))}
      <Button label={t("exam.desk")} kind="secondary" onPress={() => router.push("/desk")} />
    </Screen>
  );
}
