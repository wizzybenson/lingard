/** One drill of the sound gym, climbed a step at a time (decision 0028): learn how the sounds are made, hear the
 * difference, then say words, pairs, phrases and a sentence until each is said well. A climbed drill comes back for
 * review; one that slipped is rebuilt from its words. */
import Ionicons from "@expo/vector-icons/Ionicons";
import * as Haptics from "expo-haptics";
import { useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, StyleSheet, Text, View } from "react-native";
import Animated, { FadeInRight } from "react-native-reanimated";

import { PlayButton } from "@/live/PlayButton";
import { UpNext } from "@/home/UpNext";
import { MouthMap } from "@/studio/MouthMap";
import { Practice, SpeedPicker, type Speed } from "@/studio/Practice";
import { modelPath, STAGE, STAGE_NAMES, type Attempt, type DrillView, type GymText, type SoundGuide } from "@/studio/types";
import { useApi } from "@/state/auth";
import { useFocus } from "@/state/focus";
import { useResource } from "@/state/resource";
import { Body, Button, Card, ErrorText, Loading, Overline, Screen, Title } from "@/ui/kit";
import { colors, fonts, radius, space, type } from "@/ui/theme";

const QUIZ_ROUNDS = 8;

/** Where the learner is on the drill's climb: a slim bar of steps and the current one by name, not a row of numbered
 * circles. Steps already reached can be tapped to go back to them. */
function Ladder({ drill, at, onPick, speed, onSpeed }: { drill: DrillView; at: number; onPick: (s: number) => void; speed: Speed; onSpeed: (s: Speed) => void }) {
  const { t } = useTranslation();
  const position = drill.stages.indexOf(at);
  return (
    <View style={{ gap: space(0.75) }}>
      <View style={styles.ladder}>
        {drill.stages.map((s) => {
          const done = drill.mastered || s < drill.stage;
          const reachable = done || s === drill.stage;
          return (
            <Pressable
              key={s}
              disabled={!reachable}
              onPress={() => onPick(s)}
              hitSlop={{ top: 12, bottom: 12 }}
              accessibilityRole="tab"
              accessibilityState={{ selected: s === at, disabled: !reachable }}
              accessibilityLabel={t(`gym.stage.${STAGE_NAMES[s]}`)}
              style={[styles.rung, done && styles.rungDone, s === at && styles.rungAt]}
            />
          );
        })}
      </View>
      <View style={styles.ladderLine}>
        <Text style={[type.caption, { flex: 1 }]}>
          {t("gym.stepOf", { name: t(`gym.stage.${STAGE_NAMES[at]}`), n: position + 1, total: drill.stages.length })}
        </Text>
        <SpeedPicker value={speed} onChange={onSpeed} />
      </View>
    </View>
  );
}

function Row({ icon, label, text }: { icon: "happy-outline" | "pulse" | "chevron-expand-outline" | "volume-high-outline" | "cloud-outline"; label: string; text?: string }) {
  if (!text) return null;
  return (
    <View style={styles.row}>
      <Ionicons name={icon} size={18} color={colors.accentDeep} style={{ marginTop: 2 }} />
      <Text style={[type.callout, { flex: 1 }]}>
        <Text style={{ fontFamily: fonts.semibold, color: colors.ink }}>{`${label} `}</Text>
        {text}
      </Text>
    </View>
  );
}

function Guide({ guide, drill, speed, language }: { guide: SoundGuide; drill: DrillView; speed: Speed; language: "fr" | "en" }) {
  const { t } = useTranslation();
  const api = useApi();
  const how = guide.how;
  return (
    <Card style={{ gap: space(1.5) }}>
      <View style={styles.guideHead}>
        <Text style={styles.symbol}>{`/${guide.phoneme}/`}</Text>
        <View style={{ flex: 1 }}>
          <Text style={type.headline}>{t("gym.asIn", { word: guide.example })}</Text>
        </View>
      </View>
      <PlayButton api={api} path={`${modelPath(language)}&line=${encodeURIComponent(guide.example)}`} rate={speed} label={t("gym.hearIt")} />
      <MouthMap phoneme={guide.phoneme} features={guide.features} all={drill.features} />
      <View style={{ gap: space(1) }}>
        <Row icon="happy-outline" label={t("gym.lips")} text={how.lips} />
        <Row icon="chevron-expand-outline" label={t("gym.tongue")} text={how.tongue} />
        <Row icon="chevron-expand-outline" label={t("gym.jaw")} text={how.jaw} />
        <Row icon="pulse" label={t("gym.voice")} text={how.voice} />
        <Row icon="cloud-outline" label={t("gym.air")} text={how.air} />
      </View>
      <View style={{ gap: space(0.75) }}>
        <Overline>{t("gym.steps")}</Overline>
        {how.steps.map((s, i) => (
          <View key={i} style={styles.step}>
            <View style={styles.stepNum}>
              <Text style={styles.stepNumText}>{i + 1}</Text>
            </View>
            <Text style={[type.callout, { flex: 1, color: colors.ink }]}>{s}</Text>
          </View>
        ))}
      </View>
      <View style={styles.check}>
        <Ionicons name="eye-outline" size={18} color={colors.accentDeep} />
        <Text style={[type.callout, { flex: 1 }]}>{how.check}</Text>
      </View>
    </Card>
  );
}

/** Hear the difference: one word of a pair is played, the learner picks which. The ear leads the mouth. */
function Quiz({ drill, speed, language, onDone }: { drill: DrillView; speed: Speed; language: "fr" | "en"; onDone: (score: number) => void }) {
  const { t } = useTranslation();
  const api = useApi();
  // Which word of each pair is played: random once per quiz (set up on first render, not on every render).
  const [rounds] = useState(() =>
    Array.from({ length: QUIZ_ROUNDS }, (_, i) => {
      const pair: [string, string] = drill.pairs[i % drill.pairs.length] ?? ["", ""];
      return { pair, answer: Math.random() < 0.5 ? 0 : 1 };
    }),
  );
  const [round, setRound] = useState(0);
  const [right, setRight] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);
  const current = rounds[round];
  if (!current) return null;
  const word = current.pair[current.answer] ?? "";
  const pick = (i: number) => {
    if (picked !== null) return;
    setPicked(i);
    const ok = i === current.answer;
    if (ok) setRight((r) => r + 1);
    void Haptics.notificationAsync(ok ? Haptics.NotificationFeedbackType.Success : Haptics.NotificationFeedbackType.Warning);
  };
  const next = () => {
    if (round + 1 >= rounds.length) return onDone(right / rounds.length);
    setRound(round + 1);
    setPicked(null);
  };
  return (
    <Card style={{ gap: space(1.5) }}>
      <Text style={type.caption}>{t("gym.round", { n: round + 1, total: rounds.length })}</Text>
      <Text style={type.headline}>{t("gym.whichDidYouHear")}</Text>
      <PlayButton key={round} api={api} path={`${modelPath(language)}&line=${encodeURIComponent(word)}`} rate={speed} label={t("gym.playWord")} />
      <View style={{ flexDirection: "row", gap: space(1) }}>
        {current.pair.map((w, i) => {
          const state = picked === null ? "idle" : i === current.answer ? "right" : i === picked ? "wrong" : "idle";
          return (
            <Pressable
              key={w}
              accessibilityRole="button"
              accessibilityLabel={w}
              onPress={() => pick(i)}
              style={[styles.choice, state === "right" && styles.choiceRight, state === "wrong" && styles.choiceWrong]}
            >
              <Text style={styles.choiceText}>{w}</Text>
            </Pressable>
          );
        })}
      </View>
      {picked !== null && <Button label={t(round + 1 >= rounds.length ? "gym.finish" : "gym.next")} icon="arrow-forward" onPress={next} />}
    </Card>
  );
}

function itemsFor(drill: DrillView, stage: number): GymText[] {
  if (stage === STAGE.words) return drill.words;
  if (stage === STAGE.pairs) return drill.pair_texts;
  if (stage === STAGE.phrases) return drill.phrases;
  return [drill.sentence];
}

export default function Drill() {
  const { t } = useTranslation();
  const api = useApi();
  const { key } = useLocalSearchParams<{ key: string }>();
  const { language } = useFocus();
  const drill = useResource(
    () => (language ? api.get<DrillView>(`/v1/studio/gym/${encodeURIComponent(key)}?language=${language}`) : Promise.resolve(null)),
    [api, key, language],
  );
  const [picked, setPicked] = useState<number | null>(null);
  const [speed, setSpeed] = useState<Speed>(0.75);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [quizResult, setQuizResult] = useState<number | null>(null);
  const [reviewGood, setReviewGood] = useState<boolean[]>([]);
  const view = drill.data;
  if (!view || !language) {
    return (
      <Screen back title={t("studio.title")}>
        <ErrorText message={drill.error} onRetry={drill.reload} />
        <Loading />
      </Screen>
    );
  }
  const reviewing = view.mastered && view.review_due;
  const stage = picked ?? (view.mastered ? STAGE.sentence : view.stage);
  const items = reviewing ? [view.pair_texts[0] ?? view.words[0], view.sentence].filter((x): x is GymText => !!x) : itemsFor(view, stage);
  const item = items[index % Math.max(items.length, 1)];
  const said = new Set(view.passed_items);

  const step = async (body: { stage: number; score?: number }) => {
    setError(null);
    try {
      await api.post(`/v1/studio/gym/${encodeURIComponent(view.key)}/step`, { language, ...body });
      setPicked(null);
      setIndex(0);
      drill.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const attempted = (a: Attempt) => {
    if (reviewing) {
      const results = [...reviewGood, !!a.good];
      setReviewGood(results);
      if (results.length >= items.length) {
        void api
          .post(`/v1/studio/gym/${encodeURIComponent(view.key)}/review`, { language, held: results.every(Boolean) })
          .then(() => drill.reload())
          .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
      }
      return;
    }
    if (a.progress && a.progress.stage !== view.stage) {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setTimeout(() => {
        setPicked(null);
        setIndex(0);
        drill.reload();
      }, 1200);
    }
  };

  return (
    <Screen back title={view.title}>
      <Ladder drill={view} at={stage} onPick={(s) => { setPicked(s); setIndex(0); }} speed={speed} onSpeed={setSpeed} />
      {reviewing && (
        <Card tone="accent">
          <Text style={type.headline}>{t("gym.reviewTitle")}</Text>
          <Body>{t("gym.reviewBody")}</Body>
        </Card>
      )}
      {view.mastered && !reviewing && (
        <Card tone="success">
          <Text style={type.headline}>{t("gym.masteredTitle")}</Text>
          <Body>{t("gym.masteredBody", { date: view.due ? new Date(view.due).toLocaleDateString() : "" })}</Body>
        </Card>
      )}
      {view.mastered && !reviewing && <UpNext after="sounds" />}
      <ErrorText message={error} />

      {/* Each step of the climb slides in as the learner moves up (or back to) it; the old one goes at once, so the two
          never stack. */}
      <Animated.View key={`${stage}-${reviewing}`} entering={FadeInRight.duration(280)} style={styles.stage}>
        {stage === STAGE.learn && !reviewing && (
          <>
            <Body muted>{t("gym.learnIntro")}</Body>
            {view.guides.map((g) => (
              <Guide key={g.phoneme} guide={g} drill={view} speed={speed} language={language} />
            ))}
            {view.stage === STAGE.learn && <Button label={t("gym.gotIt")} icon="arrow-forward" onPress={() => void step({ stage: STAGE.learn })} />}
          </>
        )}

        {stage === STAGE.hear && !reviewing && (
          <>
            <Body muted>{t("gym.hearIntro")}</Body>
            {quizResult === null ? (
              <Quiz
                drill={view}
                speed={speed}
                language={language}
                onDone={(score) => {
                  setQuizResult(score);
                  if (view.stage === STAGE.hear) void step({ stage: STAGE.hear, score });
                }}
              />
            ) : (
              <Card style={{ gap: space(1) }}>
                <Title>{t("gym.quizScore", { right: Math.round(quizResult * QUIZ_ROUNDS), total: QUIZ_ROUNDS })}</Title>
                <Body>{t(quizResult >= 0.8 ? "gym.quizPassed" : "gym.quizAgain")}</Body>
                <Button label={t("gym.listenAgain")} kind="secondary" icon="refresh" onPress={() => setQuizResult(null)} />
              </Card>
            )}
          </>
        )}

        {(stage >= STAGE.words || reviewing) && item && (
          <>
            <View style={styles.progressRow}>
              <Body muted>{t(reviewing ? "gym.reviewIntro" : `gym.intro.${STAGE_NAMES[stage]}`)}</Body>
              {!reviewing && stage === view.stage && (
                <Text style={styles.count}>{t("gym.saidWell", { n: view.passed_items.length, total: view.needed })}</Text>
              )}
            </View>
            <Practice
              key={`${view.key}-${stage}-${item.text}`}
              api={api}
              language={language}
              drill={view.key}
              stage={reviewing ? STAGE.mastered : stage}
              text={item}
              speed={speed}
              focus={view.focus}
              all={view.features}
              onAttempt={attempted}
            />
            {items.length > 1 && (
              <View style={styles.pager}>
                <Button label={t("gym.previous")} kind="ghost" icon="arrow-back" onPress={() => setIndex((index - 1 + items.length) % items.length)} />
                <Text style={type.caption}>
                  {`${(index % items.length) + 1} / ${items.length}`}
                  {said.has(item.text) ? " ✓" : ""}
                </Text>
                <Button label={t("gym.next")} kind="ghost" icon="arrow-forward" onPress={() => setIndex(index + 1)} />
              </View>
            )}
          </>
        )}
      </Animated.View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  stage: { gap: space(2) },
  ladder: { flexDirection: "row", gap: 4 },
  rung: { flex: 1, height: 6, borderRadius: radius.pill, backgroundColor: colors.paperDeep },
  rungDone: { backgroundColor: colors.success },
  rungAt: { backgroundColor: colors.accent },
  ladderLine: { flexDirection: "row", alignItems: "center", gap: space(1) },
  guideHead: { flexDirection: "row", alignItems: "center", gap: space(1.5) },
  symbol: { fontFamily: fonts.displayBold, fontSize: 34, color: colors.accentDeep },
  row: { flexDirection: "row", gap: space(1), alignItems: "flex-start" },
  step: { flexDirection: "row", gap: space(1), alignItems: "flex-start" },
  stepNum: { width: 22, height: 22, borderRadius: 11, backgroundColor: colors.accent, alignItems: "center", justifyContent: "center", marginTop: 1 },
  stepNumText: { fontFamily: fonts.semibold, fontSize: 12, color: colors.accentInk },
  check: { flexDirection: "row", gap: space(1), backgroundColor: colors.accentSoft, borderRadius: radius.md, padding: space(1.25) },
  choice: { flex: 1, minHeight: 64, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, alignItems: "center", justifyContent: "center" },
  choiceRight: { backgroundColor: colors.successSoft, borderColor: colors.success },
  choiceWrong: { backgroundColor: colors.dangerSoft, borderColor: colors.danger },
  choiceText: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.ink },
  progressRow: { gap: space(0.5) },
  count: { fontFamily: fonts.semibold, fontSize: 13, color: colors.accentDeep },
  pager: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
});
