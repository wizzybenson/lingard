import { router } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { StepView } from "@/api/types";
import { useApi } from "@/state/auth";
import { Body, Button, Card, ErrorText, Screen, Title } from "@/ui/kit";

export default function ExamHall() {
  const { t } = useTranslation();
  const api = useApi();
  const [error, setError] = useState<string | null>(null);

  const begin = async (path: string, body: object, language: "fr" | "en") => {
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
      <ErrorText message={error} />
      {(["fr", "en"] as const).map((language) => (
        <Card key={language}>
          <Title>{language === "fr" ? "TEF Canada" : "IELTS General Training"}</Title>
          <Body muted>{t("exam.placement")}</Body>
          <Button label={t("exam.quick")} onPress={() => void begin("/v1/placement", { language, path: "quick" }, language)} />
          <Button label={t("exam.skip")} kind="secondary" onPress={() => void begin("/v1/placement", { language, path: "skip" }, language)} />
          <Button label={t("exam.start")} kind="secondary" onPress={() => void begin("/v1/exams", { pack: language === "fr" ? "tef_canada" : "ielts_gt" }, language)} />
        </Card>
      ))}
      <Button label="Desk" kind="secondary" onPress={() => router.push("/desk")} />
    </Screen>
  );
}
