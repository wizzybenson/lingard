/** Runs an interactive placement or mock: one prompt at a time, strictly as the server sends them (no hints). */
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Switch, View } from "react-native";

import type { StepView } from "@/api/types";
import { clock, remaining, wordCount } from "@/games/exam";
import { useApi } from "@/state/auth";
import { PlayButton } from "@/live/PlayButton";
import { Recorder } from "@/live/Recorder";
import { Body, Button, Card, ErrorText, Field, Screen, Title } from "@/ui/kit";

export default function Thread() {
  const { t } = useTranslation();
  const api = useApi();
  const params = useLocalSearchParams<{ id: string; first?: string; language?: string }>();
  const language: "fr" | "en" = params.language === "en" ? "en" : "fr";
  const [step, setStep] = useState<StepView | null>(params.first ? (JSON.parse(params.first) as StepView) : null);
  const [text, setText] = useState("");
  const [cloneConsent, setCloneConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  const sectionStart = useRef<{ section: string; at: number }>({ section: "", at: Date.now() });

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const prompt = step?.prompt ?? null;
  const section = prompt && "section" in prompt ? (prompt.section ?? "") : "";
  if (section && sectionStart.current.section !== section) sectionStart.current = { section, at: Date.now() };
  const minutes = prompt && "minutes" in prompt && typeof prompt.minutes === "number" ? prompt.minutes : null;
  const elapsedS = Math.round((now - sectionStart.current.at) / 1000);

  const send = async (value: unknown) => {
    setBusy(true);
    setError(null);
    try {
      const next = await api.post<StepView>(`/v1/threads/${params.id}/answer`, { value });
      setText("");
      setStep(next);
      if (next.done) router.replace("/(tabs)/passport");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!prompt) return <Screen><Body>{t("exam.done")}</Body></Screen>;
  const withTime = (payload: Record<string, unknown>) => (section ? { ...payload, elapsed_s: elapsedS } : payload);

  return (
    <Screen>
      {minutes !== null && <Body muted>{t("exam.timeLeft", { time: clock(remaining(sectionStart.current.at, minutes, now)) })}</Body>}
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
        <Card>
          <Title>{prompt.prompt}</Title>
          <Recorder api={api} language={language} onDone={(r) => void send(section ? { transcript: r.text } : r.text)} />
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
