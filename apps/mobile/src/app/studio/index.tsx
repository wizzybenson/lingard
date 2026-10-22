/** Accent Studio: the sound gym for the focus language (decision 0028). Every sound of the language as a drill, climbed
 * a step at a time and reviewed over weeks until it sticks; a short workout each day picks what is due. Heard in the
 * learner's own voice once they have one (the golden self): their voice, with the accent they are aiming for. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { router, useFocusEffect } from "expo-router";
import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { GymOverview, DrillSummary } from "@/studio/types";
import { useApi } from "@/state/auth";
import { useFocus } from "@/state/focus";
import { useResource } from "@/state/resource";
import { Body, Button, Card, Chip, Disclosure, ErrorText, IconBubble, Loading, Overline, ProgressBar, Screen, Section } from "@/ui/kit";
import { FocusSwitch } from "@/ui/FocusSwitch";
import { colors, fonts, radius, space, type } from "@/ui/theme";

const open = (key: string) => router.push({ pathname: "/studio/[key]", params: { key } });

function DrillRow({ drill }: { drill: DrillSummary }) {
  const { t } = useTranslation();
  const climbed = drill.mastered ? drill.stages.length : drill.stages.filter((s) => s < drill.stage).length;
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={drill.title} onPress={() => open(drill.key)} style={({ pressed }) => [styles.drill, pressed && { opacity: 0.8 }]}>
      <View style={{ flex: 1, gap: 4 }}>
        <View style={styles.drillHead}>
          <Text style={[type.headline, { flex: 1 }]} numberOfLines={2}>
            {drill.title}
          </Text>
          {drill.review_due ? (
            <Chip label={t("gym.reviewDue")} tone="warning" icon="refresh" />
          ) : drill.mastered ? (
            <Ionicons name="checkmark-circle" size={20} color={colors.success} />
          ) : null}
        </View>
        {drill.sounds.length > 0 && (
          <Text style={type.caption} numberOfLines={1}>
            {drill.sounds.map((s, i) => `/${s}/ ${drill.examples[i]}`).join("  ·  ")}
          </Text>
        )}
        <View style={styles.rungs}>
          {drill.stages.map((s, i) => (
            <View key={s} style={[styles.rung, i < climbed && styles.rungDone, i === climbed && !drill.mastered && styles.rungNow]} />
          ))}
          {drill.score !== null && <Text style={styles.score}>{Math.round(drill.score)}</Text>}
        </View>
      </View>
      <Ionicons name="chevron-forward" size={18} color={colors.muted} />
    </Pressable>
  );
}

export default function Studio() {
  const { t } = useTranslation();
  const api = useApi();
  const focus = useFocus();
  const language = focus.language;
  const voice = useResource(() => api.get<{ status: string }>("/v1/voice"), [api]);
  const gym = useResource(() => (language ? api.get<GymOverview>(`/v1/studio/gym?language=${language}`) : Promise.resolve(null)), [api, language]);
  const { reload } = gym;
  useFocusEffect(useCallback(() => reload(), [reload]));
  const drills = gym.data?.drills ?? [];
  const byKey = new Map(drills.map((d) => [d.key, d]));
  const workout = (gym.data?.workout ?? []).map((k) => byKey.get(k)).filter((d): d is DrillSummary => !!d);
  const mastered = drills.filter((d) => d.mastered).length;
  const sounds = drills.filter((d) => d.sounds.length > 0);
  const music = drills.filter((d) => d.sounds.length === 0);

  return (
    <Screen back title={t("studio.title")} accessory={<FocusSwitch />} onRefresh={reload}>
      <ErrorText message={gym.error} onRetry={reload} />
      {!gym.data && !gym.error && <Loading />}

      {gym.data && (
        <>
          {/* One short workout picked for today; the full gym is folded below for whoever wants to choose. */}
          <Card tone="accent" style={{ gap: space(1.5) }}>
            <Overline>{t("gym.workoutShort")}</Overline>
            {workout.map((d, i) => (
              <View key={d.key} style={styles.row}>
                <View style={styles.number}>
                  <Text style={styles.numberText}>{i + 1}</Text>
                </View>
                <Text style={[type.headline, { flex: 1 }]} numberOfLines={1}>
                  {d.title}
                </Text>
              </View>
            ))}
            {workout[0] && <Button label={t("gym.startWorkout")} icon="play" onPress={() => workout[0] && open(workout[0].key)} />}
            {workout.length === 0 && <Body>{t("gym.allClimbed")}</Body>}
          </Card>
          {voice.data?.status === "active" ? (
            <Chip label={t("studio.inYourVoice")} tone="success" icon="person-circle" />
          ) : voice.data ? (
            <Pressable accessibilityRole="button" onPress={() => router.push("/voice")} style={({ pressed }) => [styles.voice, pressed && { opacity: 0.7 }]}>
              <IconBubble name="mic-circle" tone="sunset" size={36} />
              <View style={{ flex: 1 }}>
                <Text style={type.callout}>{t("studio.voiceTitle")}</Text>
                <Text style={type.caption}>{t("studio.voiceAction")}</Text>
              </View>
              <Ionicons name="chevron-forward" size={16} color={colors.muted} />
            </Pressable>
          ) : null}
          <View style={{ gap: 4, marginHorizontal: space(1) }}>
            <Text style={type.caption}>{t("gym.mastered", { n: mastered, total: drills.length })}</Text>
            <ProgressBar value={drills.length ? mastered / drills.length : 0} tone="success" />
          </View>
          <Disclosure title={t("gym.sounds")} hint={String(sounds.length)}>
            <Section>
              {sounds.map((d) => (
                <DrillRow key={d.key} drill={d} />
              ))}
            </Section>
          </Disclosure>
          {music.length > 0 && (
            <Disclosure title={t("gym.music")} hint={String(music.length)}>
              <Section>
                {music.map((d) => (
                  <DrillRow key={d.key} drill={d} />
                ))}
              </Section>
            </Disclosure>
          )}
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: space(1.5) },
  drill: { flexDirection: "row", alignItems: "center", gap: space(1), paddingVertical: space(1.25), paddingHorizontal: space(1.5) },
  drillHead: { flexDirection: "row", alignItems: "center", gap: space(1) },
  rungs: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 2 },
  rung: { width: 18, height: 5, borderRadius: radius.pill, backgroundColor: colors.paperDeep },
  rungDone: { backgroundColor: colors.success },
  rungNow: { backgroundColor: colors.accent },
  number: { width: 24, height: 24, borderRadius: 12, alignItems: "center", justifyContent: "center", backgroundColor: colors.card },
  numberText: { fontFamily: fonts.semibold, fontSize: 13, color: colors.accentDeep },
  voice: { flexDirection: "row", alignItems: "center", gap: space(1.25), paddingHorizontal: space(1), minHeight: 52 },
  score: { marginLeft: space(0.5), fontFamily: fonts.semibold, fontSize: 12, color: colors.inkSoft },
});
