/** The music of a take against its native model (decision 0028): word stress, sentence emphasis, rhythm and
 * intonation, each with a score, a picture and one plain sentence of what to change. The syllable strip shows how much
 * each syllable stands out (model above, learner below); the melody line follows the voice's pitch syllable by
 * syllable, with the ending that carries a question or a statement. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { useTranslation } from "react-i18next";
import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { colors, fonts, radius, space, type } from "@/ui/theme";

import type { Music as MusicResult, MusicPart, Syllable } from "./types";

const PARTS: MusicPart[] = ["stress", "emphasis", "rhythm", "intonation"];
const GOOD = 70;

function tone(score: number): string {
  return score >= GOOD ? colors.success : score >= 50 ? colors.warning : colors.danger;
}

function Meter({ part, score, focused }: { part: MusicPart; score: number; focused: boolean }) {
  const { t } = useTranslation();
  return (
    <View style={[styles.meter, focused && styles.meterFocus]} accessibilityLabel={t("music.a11y", { part: t(`music.part.${part}`), score: Math.round(score) })}>
      <Text style={styles.meterLabel}>{t(`music.part.${part}`)}</Text>
      <Text style={[styles.meterScore, { color: tone(score) }]}>{Math.round(score)}</Text>
      <View style={styles.meterTrack}>
        <View style={[styles.meterFill, { width: `${Math.max(4, Math.min(100, score))}%`, backgroundColor: tone(score) }]} />
      </View>
    </View>
  );
}

/** A circle per syllable, sized by how much it stands out: the model's row above, the learner's below, and under each
 * word's circles the word as it is written (learners read words, not phonetic symbols). */
function Strip({ syllables }: { syllables: Syllable[] }) {
  const { t } = useTranslation();
  const size = (w: number) => 12 + Math.max(0, Math.min(1, (w + 2) / 5)) * 26;
  const words: { word: number; label: string; items: Syllable[] }[] = [];
  for (const s of syllables) {
    const last = words[words.length - 1];
    if (last && last.word === s.word) last.items.push(s);
    else words.push({ word: s.word, label: s.spelling ?? s.text, items: [s] });
  }
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.strip}>
      <View style={styles.rowLabels}>
        <Text style={styles.rowLabel}>{t("gym.model")}</Text>
        <Text style={styles.rowLabel}>{t("gym.you")}</Text>
      </View>
      {words.map((w) => (
        <View key={w.word} style={styles.word}>
          <View style={{ flexDirection: "row", gap: 4 }}>
            {w.items.map((s, i) => (
              <View key={i} style={styles.syllable}>
                <View style={styles.dotCell}>
                  <View style={[styles.dot, { width: size(s.model.weight), height: size(s.model.weight), backgroundColor: colors.accent }]} />
                </View>
                <View style={styles.dotCell}>
                  <View style={[styles.dot, { width: size(s.you.weight), height: size(s.you.weight), backgroundColor: colors.sunset }]} />
                </View>
              </View>
            ))}
          </View>
          <Text style={styles.wordText} numberOfLines={1}>
            {w.label}
          </Text>
        </View>
      ))}
    </ScrollView>
  );
}

/** Semitones either side of the voice's middle the melody line shows; anything further is drawn at the edge. */
const PITCH_RANGE = 8;

/** Pitch per syllable, model and learner, each against its own voice: the shape is what matters. Drawn from the
 * panel's measured width, so each segment joins its two dots exactly. */
function Melody({ syllables, final }: { syllables: Syllable[]; final: { expected: string | null; yours: string | null } | null }) {
  const { t } = useTranslation();
  const [width, setWidth] = useState(0);
  const height = 90;
  const values = syllables.flatMap((s) => [s.model.pitch, s.you.pitch]).filter((x): x is number => x !== null);
  if (values.length < 3) return null;
  const pad = 12;
  const clamp = (v: number) => Math.max(-PITCH_RANGE, Math.min(PITCH_RANGE, v));
  const top = Math.max(3, ...values.map((v) => Math.abs(clamp(v))));
  const y = (v: number) => height / 2 - (clamp(v) / top) * (height / 2 - pad);
  const x = (i: number) => pad + (i * (width - 2 * pad)) / Math.max(syllables.length - 1, 1);
  const line = (key: "model" | "you", colour: string) =>
    syllables.map((s, i) => {
      const v = s[key].pitch;
      if (v === null) return null;
      const next = syllables[i + 1]?.[key].pitch;
      const [x1, y1] = [x(i), y(v)];
      const segment =
        next !== undefined && next !== null
          ? (() => {
              const [x2, y2] = [x(i + 1), y(next)];
              const length = Math.hypot(x2 - x1, y2 - y1);
              return (
                <View
                  style={[
                    styles.segment,
                    {
                      left: (x1 + x2) / 2 - length / 2,
                      top: (y1 + y2) / 2 - 1,
                      width: length,
                      backgroundColor: colour,
                      transform: [{ rotate: `${Math.atan2(y2 - y1, x2 - x1)}rad` }],
                    },
                  ]}
                />
              );
            })()
          : null;
      return (
        <View key={`${key}${i}`} style={StyleSheet.absoluteFill} pointerEvents="none">
          {segment}
          <View style={[styles.pitchDot, { left: x1 - 5, top: y1 - 5, backgroundColor: colour }]} />
        </View>
      );
    });
  return (
    <View style={{ gap: space(0.75) }}>
      <View style={styles.melodyHead}>
        <Text style={type.overline}>{t("music.melody")}</Text>
        {final?.expected && (
          <View style={styles.final}>
            <Ionicons name={final.expected === "rise" ? "trending-up" : final.expected === "fall" ? "trending-down" : "remove"} size={16} color={colors.accentDeep} />
            <Text style={type.caption}>{t(`music.end.${final.expected}`)}</Text>
          </View>
        )}
      </View>
      <View style={[styles.melody, { height }]} onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
        {width > 0 && line("model", colors.accent)}
        {width > 0 && line("you", colors.sunset)}
      </View>
    </View>
  );
}

function Advice({ music }: { music: MusicResult }) {
  const { t } = useTranslation();
  const lines: { key: string; node: React.ReactNode }[] = [];
  for (const w of music.stress?.words ?? []) {
    if (w.expected === w.yours) continue;
    lines.push({
      key: `stress-${w.word}`,
      node: (
        <Text style={type.callout}>
          {t("music.stressIn", { word: w.word })}{" "}
          {w.syllables.map((s, i) => (
            <Text key={i} style={i === w.expected ? styles.stressed : styles.unstressed}>
              {i > 0 ? "·" : ""}
              {s}
            </Text>
          ))}
          {" "}
          {t("music.stressYours", { syllable: w.syllables[w.yours] ?? "" })}
        </Text>
      ),
    });
  }
  if (music.emphasis && music.emphasis.score < GOOD && music.emphasis.expected !== music.emphasis.yours) {
    lines.push({ key: "emphasis", node: <Text style={type.callout}>{t("music.emphasis", { expected: music.emphasis.expected, yours: music.emphasis.yours })}</Text> });
  }
  if (music.rhythm && music.rhythm.score < GOOD) {
    const pace = music.rhythm.pace;
    const word = music.syllables.find((s) => s.word === music.rhythm?.stretch_word)?.spelling ?? music.rhythm.stretch;
    const say = pace < 0.8 ? t("music.tooFast") : pace > 1.3 ? t("music.tooSlow") : t("music.stretch", { syllable: word });
    lines.push({ key: "rhythm", node: <Text style={type.callout}>{say}</Text> });
  }
  const final = music.intonation?.final;
  if (final?.expected && final.yours && final.expected !== final.yours) {
    lines.push({
      key: "intonation",
      node: <Text style={type.callout}>{t("music.ending", { expected: t(`music.move.${final.expected}`), yours: t(`music.moved.${final.yours}`) })}</Text>,
    });
  } else if (music.intonation && music.intonation.score < GOOD) {
    lines.push({ key: "intonation", node: <Text style={type.callout}>{t("music.followMelody")}</Text> });
  }
  if (lines.length === 0) return null;
  return (
    <View style={styles.advice}>
      {lines.map((l) => (
        <View key={l.key} style={styles.adviceRow}>
          <Ionicons name="musical-note" size={16} color={colors.warning} style={{ marginTop: 2 }} />
          <View style={{ flex: 1 }}>{l.node}</View>
        </View>
      ))}
    </View>
  );
}

export function Music({ music, focus }: { music: MusicResult; focus: MusicPart | null }) {
  const { t } = useTranslation();
  const parts = PARTS.filter((p) => music[p] !== null).sort((a, b) => (a === focus ? -1 : b === focus ? 1 : 0));
  if (parts.length === 0 && music.syllables.length < 2) return null;
  return (
    <View style={{ gap: space(1.5) }}>
      <Text style={type.overline}>{t("music.title")}</Text>
      {parts.length > 0 && (
        <View style={styles.meters}>
          {parts.map((p) => {
            const part = music[p];
            return part ? <Meter key={p} part={p} score={part.score} focused={p === focus} /> : null;
          })}
        </View>
      )}
      <Advice music={music} />
      {music.syllables.length >= 2 && <Strip syllables={music.syllables} />}
      <Melody syllables={music.syllables} final={music.intonation?.final ?? null} />
    </View>
  );
}

const styles = StyleSheet.create({
  meters: { flexDirection: "row", flexWrap: "wrap", gap: space(1) },
  meter: { flexGrow: 1, flexBasis: "45%", gap: 4, backgroundColor: colors.paper, borderRadius: radius.md, padding: space(1.25) },
  meterFocus: { borderWidth: 2, borderColor: colors.accent },
  meterLabel: { fontFamily: fonts.medium, fontSize: 12, color: colors.inkSoft },
  meterScore: { fontFamily: fonts.displayBold, fontSize: 22 },
  meterTrack: { height: 5, borderRadius: radius.pill, backgroundColor: colors.paperDeep, overflow: "hidden" },
  meterFill: { height: 5, borderRadius: radius.pill },
  strip: { flexDirection: "row", alignItems: "flex-end", gap: space(0.75), paddingVertical: space(0.5) },
  rowLabels: { justifyContent: "space-around", height: 2 * 42, marginBottom: 20 },
  rowLabel: { fontFamily: fonts.medium, fontSize: 11, color: colors.muted },
  word: { alignItems: "center", gap: 2 },
  syllable: { alignItems: "center", minWidth: 40 },
  dotCell: { height: 42, alignItems: "center", justifyContent: "center" },
  dot: { borderRadius: 999 },
  wordText: { fontFamily: fonts.medium, fontSize: 13, color: colors.ink, maxWidth: 160 },
  melodyHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  final: { flexDirection: "row", alignItems: "center", gap: 4 },
  melody: { backgroundColor: colors.paper, borderRadius: radius.md },
  pitchDot: { position: "absolute", width: 10, height: 10, borderRadius: 5 },
  segment: { position: "absolute", height: 2, opacity: 0.55, borderRadius: 1 },
  advice: { gap: space(1), backgroundColor: colors.warningSoft, borderRadius: radius.md, padding: space(1.5) },
  adviceRow: { flexDirection: "row", gap: space(1), alignItems: "flex-start" },
  stressed: { fontFamily: fonts.semibold, color: colors.accentDeep, textDecorationLine: "underline" },
  unstressed: { color: colors.inkSoft },
});
