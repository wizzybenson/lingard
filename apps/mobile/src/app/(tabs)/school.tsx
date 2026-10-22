/** The School: the whole library of key points (the rules, words and phrases), the learner's level first, then lessons
 * built from their own mistakes, then every level above, then the basics (SPEC §16). Nothing here is required: the
 * missions teach what they need where they need it (decision 0025). Key-point lessons open at once from authored
 * content. */
import { router, useFocusEffect } from "expo-router";
import Ionicons from "@expo/vector-icons/Ionicons";
import { useCallback, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, Text, View } from "react-native";

import type { KeyPoint, LessonRow } from "@/api/types";
import { KIND_ICONS, openKeyPoint } from "@/school/keyPoints";
import { useApi } from "@/state/auth";
import { useCities } from "@/state/cities";
import { useFocus } from "@/state/focus";
import { useResource } from "@/state/resource";
import { Body, Button, Card, Chip, ErrorText, IconBubble, ListRow, Loading, Overline, ProgressBar, Screen, Section, Segmented, Title } from "@/ui/kit";
import { colors, space, type } from "@/ui/theme";

type Language = "fr" | "en";

const KINDS: KeyPoint["kind"][] = ["grammar", "lexset", "function"];


export default function School() {
  const { t } = useTranslation();
  const api = useApi();
  const cities = useCities();
  const [opening, setOpening] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const focus = useFocus();
  const language: Language | null = focus.language;

  const path = useResource(() => (language ? api.get<KeyPoint[]>(`/v1/key-points?language=${language}&every_level=true`) : Promise.resolve(null)), [api, language]);
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
  // The rules of the level come first (Today asks for them before the story); then its words and phrases.
  const next = KINDS.map((kind) => core.find((k) => k.kind === kind && k.status !== "done")).find(Boolean) ?? null;
  const learned = core.filter((k) => k.status === "done").length;
  const remedial = (lessons.data ?? [])
    .filter((l) => l.content.kind !== "key_points" && (!language || l.node_key.startsWith(`${language}.`)))
    .sort((a, b) => Number(a.status === "done") - Number(b.status === "done"));

  const row = (point: KeyPoint) => (
    <ListRow
      key={point.node_key}
      title={point.title}
      subtitle={point.learned_in_use ? t("school.learnedInUse") : point.status === "done" ? t("school.done") : t("units.minutes", { count: 5 })}
      leading={
        <IconBubble
          name={point.status === "done" ? "checkmark" : KIND_ICONS[point.kind][point.status === "open" ? 1 : 0]}
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
          onChange={focus.choose}
        />
      )}
      <ErrorText message={error ?? path.error ?? lessons.error} onRetry={error ? undefined : reload} />
      {!path.data && <Loading />}

      {next && (
        <Card tone="accent">
          <Overline>{t("today.nextUp")}</Overline>
          <Title>{next.title}</Title>
          <View style={{ flexDirection: "row", gap: space(0.75) }}>
            <Chip label={t(`school.kinds.${next.kind}`)} icon={KIND_ICONS[next.kind][1]} />
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
          {KINDS.map((kind) => {
            const group = core.filter((k) => k.kind === kind);
            if (group.length === 0) return null;
            const done = group.filter((k) => k.status === "done").length;
            return (
              <Section key={kind} title={`${t(`school.kinds.${kind}`)} · ${done}/${group.length}`}>
                {group.map(row)}
              </Section>
            );
          })}
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

      {[...new Set(ahead.map((k) => k.band))].map((band) => (
        <LevelGroup key={band} band={band} points={ahead.filter((k) => k.band === band)} row={row} />
      ))}
      {basics.length > 0 && <Section title={t("school.basics")}>{basics.map(row)}</Section>}
    </Screen>
  );
}

/** A level above the learner's, folded to one line until opened: the library is all there, without a wall of rows. */
function LevelGroup({ band, points, row }: { band: number; points: KeyPoint[]; row: (point: KeyPoint) => ReactNode }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const done = points.filter((k) => k.status === "done").length;
  return (
    <View style={{ gap: space(1) }}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        onPress={() => setOpen((v) => !v)}
        style={({ pressed }) => [{ flexDirection: "row", alignItems: "center", gap: space(1), marginHorizontal: space(1), minHeight: 40 }, pressed && { opacity: 0.7 }]}
      >
        <Text style={[type.overline, { flex: 1 }]}>{t("school.level", { level: band })}</Text>
        <Text style={type.caption}>{done > 0 ? t("school.learned", { done, total: points.length }) : t("school.lessonsCount", { count: points.length })}</Text>
        <Ionicons name={open ? "chevron-up" : "chevron-down"} size={18} color={colors.muted} />
      </Pressable>
      {open && <Section>{points.map(row)}</Section>}
    </View>
  );
}
