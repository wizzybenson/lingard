import { useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import { useState } from "react";

import { useTranslation } from "react-i18next";

import type { ApiClient } from "@/api/client";
import { playAloud } from "@/live/audioMode";
import { Button, ErrorText } from "@/ui/kit";

/** Plays an authenticated server audio resource (scripts never leave the server). The audio is fetched when tapped,
 * not when the screen opens: a lesson asking for all its recordings at once hit the voice provider's limit. If the
 * server can't render it (no text-to-speech provider configured, say), the reason is shown instead of silence. */
export function PlayButton({ api, path, label }: { api: ApiClient; path: string; label?: string }) {
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
      if (loadedPath !== path) {
        setBusy(true);
        await api.text(path); // renders (or finds) the recording, and surfaces the server's reason if it can't
        player.replace(await api.mediaSource(path));
        setLoadedPath(path);
      }
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
        icon={status.playing ? "volume-high" : "volume-medium-outline"}
        kind="secondary"
        busy={busy}
        onPress={() => void play()}
      />
      <ErrorText message={error} />
    </>
  );
}
