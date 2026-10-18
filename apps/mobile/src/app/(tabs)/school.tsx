import { router, useFocusEffect } from "expo-router";
import { useTranslation } from "react-i18next";

import type { LessonRow } from "@/api/types";
import { useApi } from "@/state/auth";
import { useResource } from "@/state/resource";
import { Body, Button, Card, ErrorText, Loading, Screen, Title } from "@/ui/kit";

export default function School() {
  const { t } = useTranslation();
  const api = useApi();
  const lessons = useResource(() => api.get<LessonRow[]>("/v1/lessons"));
  useFocusEffect(lessons.reload);
  return (
    <Screen onRefresh={lessons.reload}>
      <Title>{t("school.title")}</Title>
      {lessons.loading && !lessons.data && <Loading />}
      <ErrorText message={lessons.error} onRetry={lessons.reload} />
      {lessons.data?.length === 0 && <Body muted>{t("school.noLessons")}</Body>}
      {[...(lessons.data ?? [])]
        .sort((a, b) => Number(a.status === "done") - Number(b.status === "done"))
        .map((lesson) => (
        <Card key={lesson.id}>
          <Title>{lesson.content.title}</Title>
          <Body muted>
            {t("units.minutes", { count: lesson.content.minutes })}{lesson.status === "done" ? ` · ${t("school.done")}` : ""}
          </Body>
          <Button label={t("school.start")} onPress={() => router.push({ pathname: "/lesson/[id]", params: { id: lesson.id } })} />
        </Card>
      ))}
    </Screen>
  );
}
