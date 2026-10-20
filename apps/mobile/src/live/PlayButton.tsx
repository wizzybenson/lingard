import { useAudioPlayer } from "expo-audio";
import { useEffect, useState } from "react";

import { useTranslation } from "react-i18next";

import type { ApiClient } from "@/api/client";
import { Button, ErrorText } from "@/ui/kit";

/** Plays an authenticated server audio resource (scripts never leave the server). If the server can't render it
 * (no text-to-speech provider configured, say), the button is disabled and the reason is shown instead of a silent
 * failure. The check request warms the server's synthesis cache, so the player's own fetch is cheap. */
export function PlayButton({ api, path, label }: { api: ApiClient; path: string; label?: string }) {
  const { t } = useTranslation();
  // Results are tagged with their path, so a new path shows nothing until its own check finishes.
  const [checked, setChecked] = useState<{ path: string; source?: { uri: string; headers: Record<string, string> }; error?: string } | null>(null);
  useEffect(() => {
    let live = true;
    api
      .text(path)
      .then(() => api.mediaSource(path))
      .then((source) => live && setChecked({ path, source }))
      .catch((e: unknown) => live && setChecked({ path, error: e instanceof Error ? e.message : String(e) }));
    return () => {
      live = false;
    };
  }, [api, path]);
  const current = checked?.path === path ? checked : null;
  const source = current?.source ?? null;
  const error = current?.error ?? null;
  const player = useAudioPlayer(source);
  return (
    <>
      <Button
        label={label ?? t("studio.listen")}
        icon="volume-high"
        kind="secondary"
        busy={current === null}
        disabled={!source}
        onPress={() => player.play()}
      />
      <ErrorText message={error} />
    </>
  );
}
