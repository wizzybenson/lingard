/** Runs an interactive placement or mock: one prompt at a time, strictly as the server sends them (no hints). */
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Switch, View } from "react-native";

import type { SetAnswer, StepView } from "@/api/types";
import { answeredCount, SetView } from "@/exam/SetView";
import { clock, remaining, wordCount } from "@/games/exam";
import { useApi } from "@/state/auth";
import { PlayButton } from "@/live/PlayButton";
import { Recorder } from "@/live/Recorder";
import { Body, Button, Card, Chip, ErrorText, Field, Overline, ProgressBar, Screen, Title } from "@/ui/kit";
import { space } from "@/ui/theme";

function sectionOf(step: StepView | null): string {
  const prompt = step?.prompt;
  return prompt && "section" in prompt ? (prompt.section ?? "") : "";
}

export default function Thread() {
  const { t } = useTranslation();
  const api = useApi();
  const params = useLocalSearchParams<{ id: string; first?: string; language?: string }>();
  const language: "fr" | "en" = params.language === "en" ? "en" : "fr";
  const [step, setStep] = useState<StepView | null>(() => (params.first ? (JSON.parse(params.first) as StepView) : null));
  const [text, setText] = useState("");
  const [setAnswers, setSetAnswers] = useState<{ set: string; values: SetAnswer[] }>({ set: "", values: [] });
  const [cloneConsent, setCloneConsent] = useState(false);
  const [visited, setVisited] = useState<string | null>(null);
  const [recordInstead, setRecordInstead] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [sectionStart, setSectionStart] = useState(() => ({ section: sectionOf(step), at: Date.now() }));

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const prompt = step?.prompt ?? null;
  const section = sectionOf(step);
  const minutes = prompt && "minutes" in prompt && typeof prompt.minutes === "number" ? prompt.minutes : null;
  const elapsedS = Math.round((now - sectionStart.at) / 1000);

  const send = async (value: unknown) => {
    setBusy(true);
    setError(null);
    try {
      const next = await api.post<StepView>(`/v1/threads/${params.id}/answer`, { value });
      setText("");
      setRecordInstead(false);
      setStep(next);
      const nextSection = sectionOf(next);
      if (nextSection && nextSection !== sectionStart.section) {
        // eslint-disable-next-line react-hooks/purity -- runs in the answer handler after the await, not during render
        setSectionStart({ section: nextSection, at: Date.now() });
      }
      if (next.done) router.replace("/(tabs)/passport");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!prompt) return <Screen back><Body>{t("exam.done")}</Body></Screen>;
  const withTime = (payload: Record<string, unknown>) => (section ? { ...payload, elapsed_s: elapsedS } : payload);

  if (prompt.kind === "set") {
    const served = prompt.set;
    const values = setAnswers.set === served.set_id ? setAnswers.values : served.questions.map(() => null);
    const left = remaining(sectionStart.at, prompt.minutes, now);
    const answered = answeredCount(values);
    return (
      <Screen
        key={served.set_id}
        back
        footer={
          <Button
            label={`${t("exam.next")} · ${t("exam.answered", { done: answered, total: served.questions.length })}`}
            icon="arrow-forward"
            busy={busy}
            onPress={() => void send(withTime({ answers: values }))}
          />
        }
      >
        <View style={{ gap: space(1) }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: space(1) }}>
            <Overline>{t(`exam.sections.${prompt.section}`)}</Overline>
            <View style={{ flex: 1 }} />
            <Chip label={clock(left)} tone={left < 300 ? "danger" : "plain"} icon="timer-outline" />
          </View>
          <ProgressBar value={prompt.progress.done / Math.max(prompt.progress.total, 1)} />
        </View>
        <ErrorText message={error} />
        <SetView
          api={api}
          set={served}
          first={prompt.progress.done + 1}
          answers={values}
          onChange={(i, v) => setSetAnswers({ set: served.set_id, values: values.map((x, j) => (j === i ? v : x)) })}
        />
      </Screen>
    );
  }

  return (
    <Screen back>
      {minutes !== null && <Body muted>{t("exam.timeLeft", { time: clock(remaining(sectionStart.at, minutes, now)) })}</Body>}
      <ErrorText message={error} />
      {prompt.kind === "item" && (
        <Card>
          {prompt.item.text && <Body>{prompt.item.text}</Body>}
          {prompt.item.audio_ref && <PlayButton api={api} path={`/v1/items/${prompt.item.item_id}/audio`} label="🔊" />}
          <Title>{prompt.item.question}</Title>
          {prompt.item.options.map((option, i) => (
            <Button key={option} label={option} kind="secondary" busy={busy} onPress={() => void send(section ? withTime({ choice: i }) : i)} />
          ))}
        </Card>
      )}
      {prompt.kind === "writing" && (
        <Card>
          <Body>{prompt.prompt}</Body>
          <Field label="›" value={text} onChangeText={setText} multiline style={{ minHeight: 240, textAlignVertical: "top" }} />
          <Body muted>{t("exam.words", { count: wordCount(text), min: prompt.min_words })}</Body>
          <Button label={t("exam.submit")} busy={busy} onPress={() => void send(section ? withTime({ text }) : text)} />
        </Card>
      )}
      {prompt.kind === "speaking" && (
        <Card style={{ gap: space(2) }}>
          {prompt.section ? <Overline>{t(`exam.sections.${prompt.section}`)}</Overline> : null}
          <Title>{prompt.prompt}</Title>
          {prompt.scene_id && !recordInstead ? (
            <>
              <Body muted>{t("exam.liveHint")}</Body>
              <Button
                label={t("exam.speakWithExaminer")}
                icon="mic"
                onPress={() => {
                  setVisited(prompt.scene_id ?? null);
                  router.push({ pathname: "/scene/[id]", params: { id: prompt.scene_id! } });
                }}
              />
              {visited === prompt.scene_id && (
                <Button label={t("exam.partDone")} kind="tinted" icon="checkmark" busy={busy} onPress={() => void send({ scene_id: prompt.scene_id })} />
              )}
              <Button label={t("exam.recordInstead")} kind="ghost" onPress={() => setRecordInstead(true)} />
            </>
          ) : (
            <Recorder api={api} language={language} onDone={(r) => void send(section ? { transcript: r.text } : r.text)} />
          )}
        </Card>
      )}
      {prompt.kind === "read_aloud" && (
        <Card>
          <Body muted>{t("exam.readAloud")}</Body>
          <Title>{prompt.text}</Title>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Switch value={cloneConsent} onValueChange={setCloneConsent} accessibilityLabel={t("exam.cloneConsent")} />
            <Body>{t("exam.cloneConsent")}</Body>
          </View>
          <Recorder api={api} language={language} onDone={(r) => void send({ audio_ref: r.uri, transcript: r.text, consent_clone: cloneConsent })} />
        </Card>
      )}
    </Screen>
  );
}
