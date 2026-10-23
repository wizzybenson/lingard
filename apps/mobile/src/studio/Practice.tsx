/** One thing to say in the sound gym: hear it (slowed if wanted, in the learner's own voice once they have a clone),
 * say it, then see which words and sounds were off, what each was heard as, how to fix it, and (for melody drills)
 * the pitch of the model against the learner's. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, StyleSheet, Text, View } from "react-native";
import Animated, { FadeInDown } from "react-native-reanimated";

import type { ApiClient } from "@/api/client";
import { PlayButton } from "@/live/PlayButton";
import { Recorder } from "@/live/Recorder";
import { Card, Overline } from "@/ui/kit";
import { colors, fonts, radius, space, type } from "@/ui/theme";

import { MouthMap } from "./MouthMap";
import { Music } from "./Music";
import { GOOD, modelPath, type Attempt, type Features, type GymText, type MusicPart, type ScoredWord, type Tip } from "./types";

export const SPEEDS = [0.5, 0.75, 1] as const;
export type Speed = (typeof SPEEDS)[number];

/** Playback speed as one small chip: each tap goes to the next speed (0.5×, 0.75×, 1×). */
export function SpeedPicker({ value, onChange }: { value: Speed; onChange: (s: Speed) => void }) {
  const { t } = useTranslation();
  const next = SPEEDS[(SPEEDS.indexOf(value) + 1) % SPEEDS.length] ?? 1;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${t("gym.speed")}: ${value}×`}
      onPress={() => onChange(next)}
      hitSlop={8}
      style={({ pressed }) => [styles.speed, pressed && { opacity: 0.7 }]}
    >
      <Ionicons name="speedometer-outline" size={14} color={colors.accentDeep} />
      <Text style={styles.speedText}>{`${value}×`}</Text>
    </Pressable>
  );
}

function tone(score: number | null): { ink: string; soft: string } {
  if (score === null) return { ink: colors.ink, soft: colors.paperDeep };
  if (score >= GOOD) return { ink: colors.success, soft: colors.successSoft };
  if (score >= 50) return { ink: colors.warning, soft: colors.warningSoft };
  return { ink: colors.danger, soft: colors.dangerSoft };
}

/** The text before a try: each word with its sounds, the trained ones picked out. */
export function MarkedText({ text }: { text: GymText }) {
  return (
    <View style={styles.words}>
      {text.words.map((w, i) => (
        <View key={`${w.text}-${i}`} style={styles.word}>
          <Text style={styles.wordText}>{w.text}</Text>
          <Text style={styles.ipa}>
            {"/"}
            {w.phonemes.map((p, j) => (
              <Text key={j} style={w.targets.includes(j) ? styles.ipaTarget : undefined}>
                {p}
              </Text>
            ))}
            {"/"}
          </Text>
        </View>
      ))}
    </View>
  );
}

/** The text after a try, word by word in the colour of how it was said; tap a word for its sounds. */
function ScoredText({ words, all }: { words: ScoredWord[]; all: Record<string, Features> }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState<number | null>(() => {
    const worst = words.reduce((w, x, i) => ((x.score ?? 100) < (words[w]?.score ?? 100) ? i : w), 0);
    return (words[worst]?.score ?? 100) < GOOD ? worst : null;
  });
  const shown = open !== null ? words[open] : undefined;
  const wrong = shown?.phonemes.find((p) => p.score < GOOD && p.heard_as);
  const wrongFeatures = wrong ? all[wrong.phoneme] : undefined;
  return (
    <View style={{ gap: space(1) }}>
      <View style={styles.words}>
        {words.map((w, i) => {
          const c = tone(w.score);
          return (
            <Pressable
              key={`${w.text}-${i}`}
              accessibilityRole="button"
              accessibilityLabel={t("gym.wordA11y", { word: w.text, score: Math.round(w.score ?? 0) })}
              onPress={() => setOpen(open === i ? null : i)}
              style={[styles.scored, { backgroundColor: c.soft }, open === i && { borderColor: c.ink }]}
            >
              <Text style={[styles.wordText, { color: c.ink }]}>{w.text}</Text>
            </Pressable>
          );
        })}
      </View>
      {shown && (
        <View style={styles.detail}>
          <View style={styles.sounds}>
            {shown.phonemes.map((p, j) => {
              const byEar = p.checked === false;
              const c = byEar ? { ink: colors.inkSoft, soft: colors.paperDeep } : tone(p.score);
              return (
                <View key={j} style={[styles.sound, { backgroundColor: c.soft }]}>
                  <Text style={[styles.soundText, { color: c.ink }]}>{p.phoneme}</Text>
                  {byEar ? (
                    <Ionicons name="ear-outline" size={14} color={colors.inkSoft} />
                  ) : p.score < GOOD && p.heard_as ? (
                    <Text style={styles.heardAs}>{`→ ${p.heard_as}`}</Text>
                  ) : null}
                </View>
              );
            })}
          </View>
          {shown.phonemes.some((p) => p.checked === false) && (
            <View style={styles.byEar}>
              <Ionicons name="ear-outline" size={16} color={colors.accentDeep} />
              <Text style={[type.caption, { flex: 1 }]}>{t("gym.byEar")}</Text>
            </View>
          )}
          {wrong && wrongFeatures && <MouthMap phoneme={wrong.phoneme} features={wrongFeatures} heard={wrong.heard_as} all={all} />}
        </View>
      )}
    </View>
  );
}

function Tips({ tips }: { tips: Tip[] }) {
  const { t } = useTranslation();
  if (tips.length === 0) return null;
  return (
    <View style={{ gap: space(1) }}>
      <Overline>{t("gym.fix")}</Overline>
      {tips.map((tip) => (
        <View key={`${tip.phoneme}-${tip.heard_as}`} style={styles.tip}>
          <Text style={[type.callout, { fontFamily: fonts.semibold }]}>
            {tip.heard_as ? t("gym.heardAs", { sound: tip.phoneme, heard: tip.heard_as, word: tip.word }) : t("gym.work", { sound: tip.phoneme, word: tip.word })}
          </Text>
          <Text style={type.callout}>{tip.text}</Text>
          {tip.steps.map((s, i) => (
            <Text key={i} style={type.caption}>{`${i + 1}. ${s}`}</Text>
          ))}
        </View>
      ))}
    </View>
  );
}

export function Practice({
  api,
  language,
  drill,
  stage,
  text,
  speed,
  focus,
  all,
  onAttempt,
}: {
  api: ApiClient;
  language: "fr" | "en";
  drill: string;
  stage: number;
  text: GymText;
  speed: Speed;
  focus: MusicPart | null;
  all: Record<string, Features>;
  onAttempt: (a: Attempt) => void;
}) {
  const { t } = useTranslation();
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const reference = `${modelPath(language)}&line=${encodeURIComponent(text.text)}`;
  return (
    <Card style={{ gap: space(1.5) }}>
      {attempt ? <ScoredText key={attempt.uri + attempt.intelligibility} words={attempt.words} all={all} /> : <MarkedText text={text} />}
      <View style={styles.actions}>
        <View style={{ flex: 1 }}>
          <PlayButton api={api} path={reference} rate={speed} label={t("gym.listen")} />
        </View>
        <View style={{ flex: 1 }}>
          <Recorder<Omit<Attempt, "uri">>
            api={api}
            language={language}
            path="/v1/studio/shadow"
            fields={{ line: text.text, drill, stage: String(stage) }}
            saveKey={`gym:${language}:${drill}:${text.text}`}
            onDone={(a) => {
              setAttempt(a);
              onAttempt(a);
            }}
          />
        </View>
      </View>
      {attempt && (
        <Animated.View entering={FadeInDown.duration(200)} style={{ gap: space(1.5) }}>
          <View style={styles.verdict}>
            <Ionicons
              name={attempt.by_ear ? "ear" : attempt.good ? "checkmark-circle" : "refresh-circle"}
              size={22}
              color={attempt.by_ear ? colors.accentDeep : attempt.good ? colors.success : colors.warning}
            />
            <Text style={[type.headline, { flex: 1 }]}>{t(attempt.by_ear ? "gym.clearByEar" : attempt.good ? "gym.good" : "gym.again")}</Text>
          </View>
          <PlayButton api={api} uri={attempt.uri} rate={speed} label={t("gym.hearYourself")} icon="person-outline" />
          {attempt.prosody && <Music music={attempt.prosody} focus={focus} />}
          <Tips tips={attempt.tips} />
        </Animated.View>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  speed: { flexDirection: "row", alignItems: "center", gap: 4, borderRadius: radius.pill, paddingHorizontal: space(1.25), minHeight: 30, backgroundColor: colors.accentSoft },
  speedText: { fontFamily: fonts.semibold, fontSize: 13, color: colors.accentDeep },
  words: { flexDirection: "row", flexWrap: "wrap", gap: space(1), rowGap: space(1) },
  word: { alignItems: "center" },
  wordText: { fontFamily: fonts.displayBold, fontSize: 24, lineHeight: 30, color: colors.ink },
  ipa: { fontSize: 14, color: colors.muted },
  ipaTarget: { color: colors.accentDeep, fontFamily: fonts.semibold, textDecorationLine: "underline" },
  scored: { borderRadius: radius.md, paddingHorizontal: space(1), paddingVertical: 2, borderWidth: 2, borderColor: "transparent" },
  detail: { gap: space(1.5), backgroundColor: colors.paper, borderRadius: radius.md, padding: space(1.5) },
  sounds: { flexDirection: "row", flexWrap: "wrap", gap: space(0.75) },
  sound: { flexDirection: "row", alignItems: "baseline", gap: 4, borderRadius: radius.sm, paddingHorizontal: space(1), paddingVertical: 4 },
  soundText: { fontFamily: fonts.semibold, fontSize: 18 },
  heardAs: { fontSize: 13, color: colors.warning },
  actions: { flexDirection: "row", gap: space(1), alignItems: "flex-start" },
  verdict: { flexDirection: "row", alignItems: "center", gap: space(1) },
  tip: { gap: 4, backgroundColor: colors.warningSoft, borderRadius: radius.md, padding: space(1.5) },
  byEar: { flexDirection: "row", gap: space(0.75), alignItems: "flex-start", backgroundColor: colors.accentSoft, borderRadius: radius.md, padding: space(1) },
});
