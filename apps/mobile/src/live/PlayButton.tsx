import { useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import { useState } from "react";

import { useTranslation } from "react-i18next";

import type { ApiClient } from "@/api/client";
import { playAloud } from "@/live/audioMode";
import { Button, ErrorText } from "@/ui/kit";

/** Plays an authenticated server audio resource (scripts never leave the server). The audio is fetched when tapped,
 * not when the screen opens: a lesson asking for all its recordings at once hit the voice provider's limit. If the
 * server can't render it (no text-to-speech provider configured, say), the reason is shown instead of silence. */
export function PlayButton({
  api,
  path,
  uri,
  label,
  rate = 1,
  icon,
}: {
  api: ApiClient;
  /** A server recording (rendered on first play). */
  path?: string;
  /** Or a recording already on the device (the learner's own take). */
  uri?: string;
  label?: string;
  /** Playback speed; pitch is kept, so a slowed line still sounds like the same voice. */
  rate?: number;
  icon?: "volume-medium-outline" | "person-outline";
}) {
  const { t } = useTranslation();
  const player = useAudioPlayer(null);
  const status = useAudioPlayerStatus(player);
  const [loadedPath, setLoadedPath] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const play = async () => {
    setError(null);
    try {
      await playAloud();
      const source = uri ?? path ?? "";
      if (loadedPath !== source) {
        setBusy(true);
        if (uri) player.replace({ uri });
        else if (path) {
          await api.text(path); // renders (or finds) the recording, and surfaces the server's reason if it can't
          player.replace(await api.mediaSource(path));
        }
        setLoadedPath(source);
      }
      player.setPlaybackRate(rate, "high");
      player.seekTo(0);
      player.play();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Button
        label={label ?? t("studio.listen")}
        icon={status.playing ? "volume-high" : (icon ?? "volume-medium-outline")}
        kind="secondary"
        busy={busy}
        onPress={() => void play()}
      />
      <ErrorText message={error} />
    </>
  );
}
