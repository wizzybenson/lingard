/** Record a spoken answer, upload it (by default for transcription), hand back the server's answer and the local file uri.
 * Every take is saved on the device before it is sent: if sending fails it waits there, survives the app closing, and
 * is sent again with one tap. */
import { AudioModule, RecordingPresets, setAudioModeAsync, useAudioRecorder, useAudioRecorderState } from "expo-audio";
import * as Haptics from "expo-haptics";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Platform, Text, View } from "react-native";

import type { ApiClient } from "@/api/client";
import { Button, ErrorText } from "@/ui/kit";
import { colors, space, type } from "@/ui/theme";

import { keep, saved, sent } from "./savedRecordings";

export interface Recording {
  text: string;
  confidence: number | null;
  uri: string;
}

async function formFor(uri: string, field: string): Promise<FormData> {
  const form = new FormData();
  if (Platform.OS === "web") {
    form.append(field, await (await fetch(uri)).blob(), "answer.webm");
  } else {
    form.append(field, { uri, name: "answer.m4a", type: "audio/mp4" } as unknown as Blob);
  }
  return form;
}

interface RecorderProps<T> {
  api: ApiClient;
  language: "fr" | "en";
  onDone: (r: T & { uri: string }) => void;
  /** Upload endpoint; defaults to speech-to-text. */
  path?: string;
  /** Extra multipart fields sent with the recording. */
  fields?: Record<string, string>;
  /** Multipart field the recording goes in. */
  fileField?: string;
  disabled?: boolean;
  /** Where the take waits if it can't be sent: one per thing recorded. Defaults to the endpoint and its fields. */
  saveKey?: string;
}

export function Recorder<T = Omit<Recording, "uri">>({
  api,
  language,
  onDone,
  path = "/v1/speech/transcribe",
  fields = {},
  fileField = "audio",
  disabled = false,
  saveKey,
}: RecorderProps<T>) {
  const { t } = useTranslation();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const state = useAudioRecorderState(recorder);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [waiting, setWaiting] = useState<string | null>(null);
  const key = saveKey ?? `${path}:${JSON.stringify(fields)}`;

  useEffect(() => {
    let live = true;
    void saved(key).then((uri) => live && setWaiting(uri));
    return () => {
      live = false;
    };
  }, [key]);

  const send = async (uri: string) => {
    setBusy(true);
    setError(null);
    try {
      const form = await formFor(uri, fileField);
      form.append("language", language);
      for (const [name, value] of Object.entries(fields)) form.append(name, value);
      const result = await api.postForm<T>(path, form);
      await sent(key);
      setWaiting(null);
      onDone({ ...result, uri });
    } catch (e) {
      setWaiting(uri);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const start = async () => {
    setError(null);
    const { granted } = await AudioModule.requestRecordingPermissionsAsync();
    if (!granted) return setError(t("mic.permission"));
    await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
    await recorder.prepareToRecordAsync();
    recorder.record();
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
  };

  const stop = async () => {
    await recorder.stop();
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const uri = recorder.uri;
    if (!uri) return setError(t("mic.nothing"));
    let kept = uri;
    try {
      kept = await keep(key, uri);
    } catch {
      // the take is still in the recorder's own file; it just won't survive the app closing
    }
    await send(kept);
  };

  return (
    <>
      {state.isRecording ? (
        <Button label={t("units.seconds", { count: Math.round((state.durationMillis ?? 0) / 1000) })} icon="stop" kind="danger" onPress={() => void stop()} />
      ) : (
        <Button label={t("exam.record")} icon="mic" busy={busy} disabled={disabled} onPress={() => void start()} />
      )}
      {waiting && !busy && !state.isRecording && (
        <View style={{ gap: space(0.75) }}>
          <Text style={[type.caption, { color: colors.inkSoft }]}>{t("mic.savedOnPhone")}</Text>
          <Button label={t("mic.sendAgain")} icon="cloud-upload-outline" kind="secondary" onPress={() => void send(waiting)} />
        </View>
      )}
      <ErrorText message={error} onRetry={waiting ? () => void send(waiting) : undefined} />
    </>
  );
}
