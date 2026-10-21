/** One Exam Hall screen: a text, plan or recording given once, then its questions, answered in any order
 * (one option, several options, or a few typed words), as on the official papers. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";

import type { ApiClient } from "@/api/client";
import type { ServedItem, ServedSet, SetAnswer } from "@/api/types";
import { wordCount } from "@/games/exam";
import { Card, Chip, Choice, ErrorText, Field, Overline, ProgressBar, Segmented } from "@/ui/kit";
import { colors, fonts, radius, space, type } from "@/ui/theme";
import { playAloud } from "@/live/audioMode";

/** Long passages get a Text / Questions switch, so a phone never scrolls past a wall of text to reach question 1. */
const LONG_TEXT = 700;

/** A recording that may be heard ``plays`` times, with no pause or rewind (as in the real tests). */
function Recording({ api, path, plays }: { api: ApiClient; path: string; plays: number }) {
  const { t } = useTranslation();
  const [source, setSource] = useState<{ uri: string; headers: Record<string, string> } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [used, setUsed] = useState(0);
  useEffect(() => {
    let live = true;
    api
      .mediaSource(path)
      .then((s) => live && setSource(s))
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [api, path]);
  const player = useAudioPlayer(source);
  const status = useAudioPlayerStatus(player);
  const playing = status.playing;
  const left = plays - used;
  const progress = status.duration ? status.currentTime / status.duration : 0;
  const play = () => {
    setUsed((n) => n + 1);
    player.seekTo(0);
    void playAloud().then(() => player.play());
  };
  return (
    <Card tone="accent" style={{ gap: space(1.5) }}>
      <View style={styles.row}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("exam.play")}
          accessibilityState={{ disabled: !source || playing || left <= 0 }}
          disabled={!source || playing || left <= 0}
          onPress={play}
          style={({ pressed }) => [styles.playButton, (!source || playing || left <= 0) && { opacity: 0.5 }, pressed && { transform: [{ scale: 0.96 }] }]}
        >
          <Ionicons name={playing ? "volume-high" : "play"} size={26} color={colors.accentInk} />
        </Pressable>
        <View style={{ flex: 1, gap: 4 }}>
          <Text style={type.headline}>{playing ? t("exam.playing") : left <= 0 ? t("exam.played") : t("exam.play")}</Text>
          <Text style={type.caption}>{t("exam.playsLeft", { count: Math.max(left, 0) })}</Text>
        </View>
      </View>
      {(playing || used > 0) && <ProgressBar value={playing ? progress : 1} />}
      <ErrorText message={error} />
    </Card>
  );
}

function Question({ number, item, value, onChange }: { number: number; item: ServedItem; value: SetAnswer; onChange: (v: SetAnswer) => void }) {
  const { t } = useTranslation();
  const response = item.response ?? "choice";
  const tooMany = response === "text" && item.word_limit != null && typeof value === "string" && wordCount(value.replace(/\d[\d.,:/£$€%-]*/g, "")) > item.word_limit;
  return (
    <View style={styles.question}>
      {item.instructions ? <Text style={[type.callout, styles.instructions]}>{item.instructions}</Text> : null}
      <View style={styles.row}>
        <View style={styles.number}>
          <Text style={styles.numberText}>{number}</Text>
        </View>
        <Text style={[type.headline, { flex: 1 }]}>{item.question}</Text>
      </View>
      {response === "text" ? (
        <>
          <Field
            label={item.word_limit ? t("exam.wordLimit", { count: item.word_limit }) : t("exam.yourAnswer")}
            value={typeof value === "string" ? value : ""}
            onChangeText={onChange}
            autoCapitalize="none"
            autoCorrect={false}
            spellCheck={false}
            returnKeyType="done"
          />
          {tooMany && <Text style={[type.caption, { color: colors.danger }]}>{t("exam.tooMany")}</Text>}
        </>
      ) : (
        <View style={{ gap: space(1) }}>
          {response === "multi" && <Chip label={t("exam.choose", { count: item.picks ?? 2 })} icon="checkbox-outline" />}
          {item.options.map((option, i) => {
            const picked = response === "multi" ? Array.isArray(value) && value.includes(i) : value === i;
            const toggle = () => {
              if (response !== "multi") return onChange(i);
              const current = Array.isArray(value) ? value : [];
              if (current.includes(i)) return onChange(current.filter((x) => x !== i));
              if (current.length < (item.picks ?? 2)) onChange([...current, i]);
            };
            return <Choice key={`${option}-${i}`} label={option} index={i} state={picked ? "picked" : "idle"} onPress={toggle} />;
          })}
        </View>
      )}
    </View>
  );
}

export function answeredCount(answers: SetAnswer[]): number {
  return answers.filter((a) => (Array.isArray(a) ? a.length > 0 : typeof a === "string" ? a.trim().length > 0 : a !== null)).length;
}

export function SetView({ api, set, first, answers, onChange }: {
  api: ApiClient;
  set: ServedSet;
  /** The number of the set's first question in the section (1-based). */
  first: number;
  answers: SetAnswer[];
  onChange: (index: number, value: SetAnswer) => void;
}) {
  const { t } = useTranslation();
  const long = (set.text?.length ?? 0) > LONG_TEXT;
  const [tab, setTab] = useState<"text" | "questions">("text");
  const showText = !long || tab === "text";
  const showQuestions = !long || tab === "questions";
  return (
    <View style={{ gap: space(2) }}>
      {set.audio_ref && <Recording api={api} path={`/v1/items/${set.questions[0]!.item_id}/audio`} plays={set.plays} />}
      {set.instructions ? (
        <View style={styles.instructionsBox}>
          <Ionicons name="information-circle" size={20} color={colors.accent} />
          <Text style={[type.callout, { flex: 1 }]}>{set.instructions}</Text>
        </View>
      ) : null}
      {long && (
        <Segmented
          options={[
            { value: "text", label: t("exam.text") },
            { value: "questions", label: t("exam.questions", { count: set.questions.length }) },
          ]}
          value={tab}
          onChange={setTab}
        />
      )}
      {showText && set.text && (
        <Card>
          <Text selectable style={styles.passage}>
            {set.text}
          </Text>
        </Card>
      )}
      {set.figure && (showText || !set.text) && (
        <Card>
          <Text selectable style={styles.figure}>
            {set.figure}
          </Text>
        </Card>
      )}
      {showQuestions && (
        <Card style={{ gap: space(2.5) }}>
          {set.questions.length > 1 && <Overline>{t("exam.rangeShort", { from: first, to: first + set.questions.length - 1 })}</Overline>}
          {set.questions.map((item, i) => (
            <Question key={item.item_id} number={first + i} item={item} value={answers[i] ?? null} onChange={(v) => onChange(i, v)} />
          ))}
        </Card>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: space(1.5) },
  playButton: { width: 56, height: 56, borderRadius: 28, backgroundColor: colors.accent, alignItems: "center", justifyContent: "center" },
  question: { gap: space(1.25) },
  instructions: { backgroundColor: colors.paper, borderRadius: radius.sm, padding: space(1.25) },
  instructionsBox: { flexDirection: "row", gap: space(1), alignItems: "flex-start", backgroundColor: colors.accentSoft, borderRadius: radius.md, padding: space(1.5) },
  number: { minWidth: 30, height: 30, borderRadius: 15, paddingHorizontal: 6, backgroundColor: colors.ink, alignItems: "center", justifyContent: "center" },
  numberText: { fontFamily: fonts.semibold, fontSize: 14, color: "#fff" },
  passage: { ...type.body, fontSize: 17, lineHeight: 27 },
  figure: { fontFamily: Platform.select({ ios: "Menlo", android: "monospace", default: "monospace" }), fontSize: 12, lineHeight: 17, color: colors.ink },
});
