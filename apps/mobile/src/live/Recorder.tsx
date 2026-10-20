/** Record a spoken answer, upload it (by default for transcription), hand back the server's answer and the local file uri. */
import { AudioModule, RecordingPresets, setAudioModeAsync, useAudioRecorder, useAudioRecorderState } from "expo-audio";
import * as Haptics from "expo-haptics";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Platform } from "react-native";

import type { ApiClient } from "@/api/client";
import { Button, ErrorText } from "@/ui/kit";

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
}

export function Recorder<T = Omit<Recording, "uri">>({
  api,
  language,
  onDone,
  path = "/v1/speech/transcribe",
  fields = {},
  fileField = "audio",
  disabled = false,
}: RecorderProps<T>) {
  const { t } = useTranslation();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const state = useAudioRecorderState(recorder);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    setBusy(true);
    try {
      const form = await formFor(uri, fileField);
      form.append("language", language);
      for (const [key, value] of Object.entries(fields)) form.append(key, value);
      const result = await api.postForm<T>(path, form);
      onDone({ ...result, uri });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {state.isRecording ? (
        <Button label={t("units.seconds", { count: Math.round((state.durationMillis ?? 0) / 1000) })} icon="stop" kind="danger" onPress={() => void stop()} />
      ) : (
        <Button label={t("exam.record")} icon="mic" busy={busy} disabled={disabled} onPress={() => void start()} />
      )}
      <ErrorText message={error} />
    </>
  );
}
