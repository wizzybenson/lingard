import { useAudioPlayer } from "expo-audio";
import { useEffect, useState } from "react";

import type { ApiClient } from "@/api/client";
import { Button, ErrorText } from "@/ui/kit";

/** Plays an authenticated server audio resource (scripts never leave the server). If the server can't render it
 * (no text-to-speech provider configured, say), the button is disabled and the reason is shown instead of a silent
 * failure. The check request warms the server's synthesis cache, so the player's own fetch is cheap. */
export function PlayButton({ api, path, label }: { api: ApiClient; path: string; label: string }) {
  const [source, setSource] = useState<{ uri: string; headers: Record<string, string> } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setSource(null);
    setError(null);
    api
      .text(path)
      .then(() => api.mediaSource(path))
      .then((s) => live && setSource(s))
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [api, path]);
  const player = useAudioPlayer(source);
  return (
    <>
      <Button label={label} kind="secondary" disabled={!source} onPress={() => player.play()} />
      <ErrorText message={error} />
    </>
  );
}
