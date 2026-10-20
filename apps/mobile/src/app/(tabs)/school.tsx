/** The School: key points first (the rules a learner needs before speaking), then lessons built from their own
 * mistakes (SPEC §16). Key-point lessons open at once: the server builds them from authored content. */
import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { Text, View } from "react-native";

import type { KeyPoint, LessonRow, Profile } from "@/api/types";
import { openKeyPoint } from "@/school/keyPoints";
import { useApi } from "@/state/auth";
import { useCities } from "@/state/cities";
import { useResource } from "@/state/resource";
import { Body, Button, Card, Chip, ErrorText, IconBubble, ListRow, Loading, Overline, ProgressBar, Screen, Section, Segmented, Title } from "@/ui/kit";
import { space, type } from "@/ui/theme";

type Language = "fr" | "en";

export default function School() {
  const { t } = useTranslation();
  const api = useApi();
  const cities = useCities();
  const profile = useResource(() => api.get<Profile>("/v1/me"), [api]);
  const [picked, setLanguage] = useState<Language | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The learner's pick, else the language whose exam they are preparing for, else the first city.
  const studying = profile.data ? cities.data?.find((c) => profile.data?.exam_dates[c.pack]) ?? cities.data?.[0] : undefined;
  const language: Language | null = picked ?? studying?.language ?? null;

  const path = useResource(() => (language ? api.get<KeyPoint[]>(`/v1/key-points?language=${language}`) : Promise.resolve(null)), [api, language]);
  const lessons = useResource(() => api.get<LessonRow[]>("/v1/lessons"), [api]);
  const { reload: reloadPath } = path;
  const { reload: reloadLessons } = lessons;
  const reload = useCallback(() => {
    reloadPath();
    reloadLessons();
  }, [reloadPath, reloadLessons]);
  useFocusEffect(reload);

  const open = async (point: KeyPoint) => {
    setOpening(point.node_key);
    setError(null);
    try {
      await openKeyPoint(api, point.node_key);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setOpening(null);
    }
  };

  const steps = path.data ?? [];
  const core = steps.filter((k) => k.core);
  const basics = steps.filter((k) => !k.core && !k.preview);
  const ahead = steps.filter((k) => k.preview);
  const next = core.find((k) => k.status !== "done") ?? null;
  const learned = core.filter((k) => k.status === "done").length;
  const remedial = (lessons.data ?? [])
    .filter((l) => l.content.kind !== "key_points" && (!language || l.node_key.startsWith(`${language}.`)))
    .sort((a, b) => Number(a.status === "done") - Number(b.status === "done"));

  const row = (point: KeyPoint) => (
    <ListRow
      key={point.node_key}
      title={point.title}
      subtitle={point.status === "done" ? t("school.done") : t("units.minutes", { count: 5 })}
      leading={
        <IconBubble
          name={point.status === "done" ? "checkmark" : point.status === "open" ? "book" : "book-outline"}
          tone={point.status === "done" ? "success" : point.node_key === next?.node_key ? "accent" : "plain"}
        />
      }
      disabled={opening !== null}
      onPress={() => void open(point)}
    />
  );

  return (
    <Screen title={t("school.title")} onRefresh={reload}>
      <Body muted>{t("school.keyPointsIntro")}</Body>
      {(cities.data?.length ?? 0) > 1 && (
        <Segmented
          options={(cities.data ?? []).map((c) => ({ value: c.language, label: c.pack_name }))}
          value={language}
          onChange={setLanguage}
        />
      )}
      <ErrorText message={error ?? path.error ?? lessons.error} onRetry={error ? undefined : reload} />
      {!path.data && <Loading />}

      {next && (
        <Card tone="accent">
          <Overline>{t("today.nextUp")}</Overline>
          <Title>{next.title}</Title>
          <View style={{ flexDirection: "row", gap: space(0.75) }}>
            <Chip label={t("school.lessonKind.key_points")} icon="key" />
            <Chip label={t("units.minutes", { count: 5 })} icon="time-outline" />
          </View>
          <Button label={t("school.start")} icon="play" busy={opening === next.node_key} onPress={() => void open(next)} />
        </Card>
      )}

      {core.length > 0 && (
        <View style={{ gap: space(1) }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: space(1.5), marginHorizontal: space(1) }}>
            <Text style={[type.overline, { flex: 1 }]}>{t("school.yourLevel")}</Text>
            <Text style={type.caption}>{t("school.learned", { done: learned, total: core.length })}</Text>
          </View>
          <ProgressBar value={learned / core.length} tone="success" />
          <Section>{core.map(row)}</Section>
        </View>
      )}

      <Section title={t("school.fromMistakes")} footer={remedial.length === 0 ? t("school.noMistakesYet") : undefined}>
        {remedial.map((lesson) => (
          <ListRow
            key={lesson.id}
            title={lesson.content.title}
            subtitle={lesson.status === "done" ? t("school.done") : t("units.minutes", { count: lesson.content.minutes })}
            leading={<IconBubble name={lesson.status === "done" ? "checkmark" : "construct"} tone={lesson.status === "done" ? "success" : "sunset"} />}
            onPress={() => router.push({ pathname: "/lesson/[id]", params: { id: lesson.id } })}
          />
        ))}
      </Section>

      {ahead.length > 0 && <Section title={t("school.comingUp")}>{ahead.map(row)}</Section>}
      {basics.length > 0 && <Section title={t("school.basics")}>{basics.map(row)}</Section>}
    </Screen>
  );
}
