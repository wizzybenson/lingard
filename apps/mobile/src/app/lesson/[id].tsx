/** A School lesson (SPEC §16): the rule, model sentences, the mistakes to avoid, scored games, then a same-day scene. */
import Ionicons from "@expo/vector-icons/Ionicons";
import * as Haptics from "expo-haptics";
import { useLocalSearchParams } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { ApiClient } from "@/api/client";
import type { LessonRow } from "@/api/types";
import type { Game, GameItem } from "@/contracts/generated";
import { choices, isCorrect, score, type GameResult } from "@/games/engine";
import { PlayButton } from "@/live/PlayButton";
import { SpeakButton } from "@/live/SpeakButton";
import { useApi } from "@/state/auth";
import { useResource } from "@/state/resource";
import { Body, Button, Card, Chip, Choice, ErrorText, Field, goBack, Loading, Overline, Screen } from "@/ui/kit";
import { colors, fonts, radius, space, type } from "@/ui/theme";

/** Sentence race: tap the words in order; tap a placed word to send it back. */
function WordTiles({ prompt, value, onChange, locked }: { prompt: string; value: string; onChange: (v: string) => void; locked: boolean }) {
  const words = prompt.split(" / ");
  const [placed, setPlaced] = useState<number[]>([]);
  const update = (next: number[]) => {
    setPlaced(next);
    onChange(next.map((i) => words[i]).join(" "));
  };
  return (
    <View style={{ gap: space(1) }}>
      <View style={[styles.tray, styles.answerTray]} accessibilityLabel={value}>
        {placed.map((i, at) => (
          <Pressable key={`p${i}`} disabled={locked} onPress={() => update(placed.filter((_, j) => j !== at))} style={[styles.tile, styles.tilePlaced]}>
            <Text style={styles.tileText}>{words[i]}</Text>
          </Pressable>
        ))}
      </View>
      <View style={styles.tray}>
        {words.map((word, i) =>
          placed.includes(i) ? (
            <View key={`w${i}`} style={[styles.tile, styles.tileGhost]}>
              <Text style={[styles.tileText, { color: "transparent" }]}>{word}</Text>
            </View>
          ) : (
            <Pressable key={`w${i}`} accessibilityRole="button" accessibilityLabel={word} disabled={locked} onPress={() => update([...placed, i])} style={styles.tile}>
              <Text style={styles.tileText}>{word}</Text>
            </Pressable>
          ),
        )}
      </View>
    </View>
  );
}

function ItemView({ api, lessonId, gameIndex, index, game, item, answer, onAnswer, checked }: {
  api: ApiClient;
  lessonId: string;
  gameIndex: number;
  index: number;
  game: Game;
  item: GameItem;
  answer: string;
  onAnswer: (v: string) => void;
  checked: boolean;
}) {
  const { t } = useTranslation();
  const right = checked && isCorrect(item, answer);
  return (
    <View style={styles.item}>
      {game.kind === "dictation" ? (
        <PlayButton api={api} path={`/v1/lessons/${lessonId}/audio?game=${gameIndex}&item=${index}`} />
      ) : game.kind === "spot_the_error" ? (
        <Text style={type.callout}>{t("school.tapToAnswer")}</Text>
      ) : game.kind === "sentence_race" ? null : (
        <Text style={type.headline}>{item.prompt}</Text>
      )}
      {game.kind === "spot_the_error" || game.kind === "fill_the_gap" ? (
        <View style={{ gap: space(1) }}>
          {choices(item).map((c, i) => (
            <Choice
              key={c}
              label={c}
              index={i}
              state={checked ? (isCorrect(item, c) ? "right" : answer === c ? "wrong" : "dim") : answer === c ? "picked" : "idle"}
              onPress={checked ? undefined : () => onAnswer(c)}
            />
          ))}
        </View>
      ) : game.kind === "sentence_race" ? (
        <WordTiles prompt={item.prompt} value={answer} onChange={onAnswer} locked={checked} />
      ) : (
        <Field label={t("school.answer")} value={answer} editable={!checked} onChangeText={onAnswer} autoCapitalize="none" autoCorrect={false} />
      )}
      {checked && game.kind !== "spot_the_error" && game.kind !== "fill_the_gap" && (
        <View style={styles.verdict}>
          <Ionicons name={right ? "checkmark-circle" : "close-circle"} size={18} color={right ? colors.success : colors.danger} />
          <Text style={[type.callout, { flex: 1, color: right ? colors.success : colors.ink }]}>{right ? t("phone.correct") : item.answer}</Text>
        </View>
      )}
    </View>
  );
}

function GameView({ api, lessonId, index, game, onScored }: { api: ApiClient; lessonId: string; index: number; game: Game; onScored: (result: GameResult) => void }) {
  const { t } = useTranslation();
  const [answers, setAnswers] = useState<string[]>(game.items.map(() => ""));
  // The timer checks the game from its own callback, so it reads the answers from here rather than a stale render.
  const latest = useRef(answers);
  const answer = (i: number, v: string) => {
    latest.current = latest.current.map((x, j) => (j === i ? v : x));
    setAnswers(latest.current);
  };
  const [result, setResult] = useState<GameResult | null>(null);
  const [left, setLeft] = useState<number | null>(null);
  const started = answers.some(Boolean);
  const limit = game.time_limit_s ?? null;

  const check = () => {
    if (result) return;
    const scored = score(game, latest.current);
    setResult(scored);
    onScored(scored);
    void Haptics.notificationAsync(scored.correct === scored.total ? Haptics.NotificationFeedbackType.Success : Haptics.NotificationFeedbackType.Warning);
  };

  // Timed games (conjugation duel, sentence race) start the clock on the first answer and check themselves at zero.
  useEffect(() => {
    if (!limit || !started || result) return;
    // eslint-disable-next-line react-hooks/purity -- runs in the effect, not during render
    const end = Date.now() + (left ?? limit) * 1000;
    const timer = setInterval(() => {
      const remaining = Math.max(0, Math.round((end - Date.now()) / 1000));
      setLeft(remaining);
      if (remaining === 0) {
        clearInterval(timer);
        check();
      }
    }, 250);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the clock starts once; ``left`` only resumes it
  }, [limit, started, result]);

  return (
    <Card style={{ gap: space(2) }}>
      <View style={styles.gameHead}>
        <Text style={[type.title, { flex: 1 }]}>{t(`games.${game.kind}`)}</Text>
        {limit !== null && !result && <Chip label={`${left ?? limit} s`} tone={left !== null && left <= 10 ? "danger" : "plain"} icon="timer-outline" />}
        {result && <Chip label={t("games.score", { score: result.correct, total: result.total })} tone={result.correct === result.total ? "success" : "warning"} />}
      </View>
      {game.items.map((item, i) => (
        <ItemView
          key={`${item.prompt}-${i}`}
          api={api}
          lessonId={lessonId}
          gameIndex={index}
          index={i}
          game={game}
          item={item}
          answer={answers[i] ?? ""}
          onAnswer={(v) => answer(i, v)}
          checked={!!result}
        />
      ))}
      {!result && <Button label={t("school.checkAll")} kind="tinted" icon="checkmark-done" disabled={!started} onPress={check} />}
    </Card>
  );
}

export default function LessonScreen() {
  const { t } = useTranslation();
  const api = useApi();
  const { id } = useLocalSearchParams<{ id: string }>();
  const lesson = useResource(() => api.get<LessonRow>(`/v1/lessons/${id}`), [id]);
  const [results, setResults] = useState<Record<number, GameResult>>({});
  const [finished, setFinished] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!lesson.data)
    return (
      <Screen back>
        <ErrorText message={lesson.error} onRetry={lesson.reload} />
        {!lesson.error && <Loading />}
      </Screen>
    );
  const content = lesson.data.content;
  const keyPoints = content.kind === "key_points";
  const scored = Object.values(results);
  const correct = scored.reduce((n, r) => n + r.correct, 0);
  const total = scored.reduce((n, r) => n + r.total, 0);
  const finish = async () => {
    setBusy(true);
    try {
      await api.post(`/v1/lessons/${id}/complete`, { correct, total: Math.max(total, 1) });
      setFinished(t("school.finished", { score: correct, total }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const done = lesson.data.status === "done";
  // Lessons open from the journey (a scene, the map, the School): finishing returns the learner to where they were.
  const footer = finished ? (
    <View style={{ flexDirection: "row", alignItems: "center", gap: space(1.5) }}>
      <Chip label={finished} tone="success" icon="trophy" />
      <View style={{ flex: 1 }}>
        <Button label={t("app.continue")} icon="arrow-forward" onPress={goBack} />
      </View>
    </View>
  ) : done ? (
    <Chip label={t("school.done")} tone="success" icon="checkmark-done" />
  ) : (
    <Button
      label={`${t("school.finish")} · ${scored.length}/${content.games.length}`}
      icon="flag"
      busy={busy}
      disabled={scored.length < content.games.length}
      onPress={() => void finish()}
    />
  );

  return (
    <Screen back footer={footer}>
      <View style={{ gap: space(1) }}>
        <View style={{ flexDirection: "row", gap: space(0.75) }}>
          <Chip label={t(`school.lessonKind.${content.kind ?? "remedial"}`)} tone={keyPoints ? "accent" : "sunset"} icon={keyPoints ? "key" : "construct"} />
          <Chip label={t("units.minutes", { count: content.minutes })} icon="time-outline" />
        </View>
        <Text accessibilityRole="header" style={type.largeTitle}>
          {content.title}
        </Text>
      </View>

      <Card style={{ gap: space(1.5) }}>
        <Overline>{t("school.rule")}</Overline>
        <Text style={styles.rule}>{content.rule}</Text>
      </Card>

      {(content.models?.length ?? 0) > 0 && (
        <Card style={{ gap: space(1.25) }}>
          <Overline>{t("school.models")}</Overline>
          {content.models!.map((m, i) => (
            <View key={m} style={styles.line}>
              <Ionicons name="chatbubble-ellipses" size={18} color={colors.accent} style={{ marginTop: 3 }} />
              <Text style={[type.body, { flex: 1 }]}>{m}</Text>
              <SpeakButton api={api} path={`/v1/lessons/${id}/say?part=model&index=${i}`} label={`${t("studio.listen")}: ${m}`} />
            </View>
          ))}
        </Card>
      )}

      {(content.words?.length ?? 0) > 0 && (
        <Card style={{ gap: space(1.25) }}>
          <Overline>{t("school.wordsToHear")}</Overline>
          <View style={styles.words}>
            {content.words!.map((w, i) => (
              <View key={w} style={styles.word}>
                <Text style={[type.callout, { color: colors.ink }]}>{w}</Text>
                <SpeakButton api={api} path={`/v1/lessons/${id}/say?part=word&index=${i}`} label={`${t("studio.listen")}: ${w}`} size={16} />
              </View>
            ))}
          </View>
        </Card>
      )}

      <Card style={{ gap: space(1.5) }}>
        <Overline>{keyPoints ? t("school.watchOut") : t("school.yourExamples")}</Overline>
        {content.examples.map((e, i) => (
          <View key={e.learner_said} style={styles.pair}>
            <View style={styles.line}>
              <Ionicons name="close-circle" size={18} color={colors.danger} style={{ marginTop: 3 }} />
              <Text style={[type.body, styles.wrong]}>{e.learner_said}</Text>
            </View>
            <View style={styles.line}>
              <Ionicons name="checkmark-circle" size={18} color={colors.success} style={{ marginTop: 3 }} />
              <Text style={[type.body, { flex: 1, fontFamily: fonts.medium }]}>{e.better}</Text>
              <SpeakButton api={api} path={`/v1/lessons/${id}/say?part=better&index=${i}`} label={`${t("studio.listen")}: ${e.better}`} />
            </View>
            {e.note ? <Body muted>{e.note}</Body> : null}
          </View>
        ))}
      </Card>

      {content.games.map((game, i) => (
        <GameView key={`${game.kind}-${i}`} api={api} lessonId={id} index={i} game={game} onScored={(r) => setResults((all) => ({ ...all, [i]: r }))} />
      ))}

      <Card tone="sunset" style={{ gap: space(1) }}>
        <View style={styles.line}>
          <Ionicons name="walk" size={20} color="#9A3E1E" />
          <Text style={[type.headline, { flex: 1 }]}>{t("school.homeworkTitle")}</Text>
        </View>
        <Body>{t("school.homework")}</Body>
        <Body muted>{content.homework.story_beat}</Body>
      </Card>
      <ErrorText message={error} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  rule: { fontFamily: fonts.display, fontSize: 20, lineHeight: 28, color: colors.ink },
  line: { flexDirection: "row", alignItems: "flex-start", gap: space(1) },
  words: { flexDirection: "row", flexWrap: "wrap", gap: space(1) },
  word: { flexDirection: "row", alignItems: "center", gap: 4, paddingLeft: space(1.5), paddingRight: space(0.75), minHeight: 40, borderRadius: radius.pill, backgroundColor: colors.paper },
  pair: { gap: space(0.75), paddingBottom: space(1), borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  wrong: { flex: 1, color: colors.muted, textDecorationLine: "line-through" },
  gameHead: { flexDirection: "row", alignItems: "center", gap: space(1) },
  item: { gap: space(1.25), paddingTop: space(1.5), borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  verdict: { flexDirection: "row", alignItems: "center", gap: space(0.75) },
  tray: { flexDirection: "row", flexWrap: "wrap", gap: space(1) },
  answerTray: { minHeight: 56, padding: space(1), borderRadius: radius.md, borderWidth: 1.5, borderStyle: "dashed", borderColor: colors.border, backgroundColor: colors.paper },
  tile: { paddingHorizontal: space(1.5), paddingVertical: space(1), borderRadius: radius.sm, backgroundColor: colors.card, borderWidth: 1.5, borderColor: colors.border, minHeight: 40, justifyContent: "center" },
  tilePlaced: { backgroundColor: colors.accentSoft, borderColor: colors.accent },
  tileGhost: { backgroundColor: colors.paperDeep, borderColor: colors.paperDeep },
  tileText: { fontFamily: fonts.medium, fontSize: 16, color: colors.ink },
});
