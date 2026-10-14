import { useAudioPlayer } from "expo-audio";
import { useEffect, useState } from "react";

import type { ApiClient } from "@/api/client";
import { Button } from "@/ui/kit";

/** Plays an authenticated server audio resource (scripts never leave the server). */
export function PlayButton({ api, path, label }: { api: ApiClient; path: string; label: string }) {
  const [source, setSource] = useState<{ uri: string; headers: Record<string, string> } | null>(null);
  useEffect(() => {
    void api.mediaSource(path).then(setSource);
  }, [api, path]);
  const player = useAudioPlayer(source);
  return <Button label={label} kind="secondary" disabled={!source} onPress={() => player.play()} />;
}
