import { router, useFocusEffect } from "expo-router";
import { useTranslation } from "react-i18next";

import type { LessonRow } from "@/api/types";
import { useApi } from "@/state/auth";
import { useResource } from "@/state/resource";
import { View } from "react-native";

import { Body, Button, Card, Chip, ErrorText, IconBubble, Loading, Screen, Title } from "@/ui/kit";
import { space } from "@/ui/theme";

export default function School() {
  const { t } = useTranslation();
  const api = useApi();
  const lessons = useResource(() => api.get<LessonRow[]>("/v1/lessons"));
  useFocusEffect(lessons.reload);
  return (
    <Screen title={t("school.title")} onRefresh={lessons.reload}>
      <Body muted>{t("school.intro")}</Body>
      {lessons.loading && !lessons.data && <Loading />}
      <ErrorText message={lessons.error} onRetry={lessons.reload} />
      {lessons.data?.length === 0 && (
        <Card style={{ alignItems: "center", paddingVertical: 32 }}>
          <IconBubble name="school" tone="accent" size={56} />
          <Body muted>{t("school.noLessons")}</Body>
        </Card>
      )}
      {[...(lessons.data ?? [])]
        .sort((a, b) => Number(a.status === "done") - Number(b.status === "done"))
        .map((lesson) => (
          <Card key={lesson.id}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: space(1.5) }}>
              <IconBubble name={lesson.status === "done" ? "checkmark-done" : "book"} tone={lesson.status === "done" ? "success" : "accent"} />
              <View style={{ flex: 1, gap: 4 }}>
                <Title>{lesson.content.title}</Title>
                <View style={{ flexDirection: "row", gap: space(0.75) }}>
                  <Chip label={t("units.minutes", { count: lesson.content.minutes })} icon="time-outline" />
                  {lesson.status === "done" && <Chip label={t("school.done")} tone="success" />}
                </View>
              </View>
            </View>
            <Button
              label={t("school.start")}
              kind={lesson.status === "done" ? "secondary" : "primary"}
              onPress={() => router.push({ pathname: "/lesson/[id]", params: { id: lesson.id } })}
            />
          </Card>
        ))}
    </Screen>
  );
}
