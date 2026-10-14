/** Join a scene's LiveKit room: echo-cancelled mic, NPC audio, captions, turn haptics, open mic or push-to-talk. */
import * as Haptics from "expo-haptics";
import { Room, RoomEvent, type Participant, type RemoteTrack, Track } from "livekit-client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Platform } from "react-native";

import type { LiveTicket } from "@/api/types";
import { appendCaption, parseCaption, type Caption } from "./captions";

export type LiveStatus = "idle" | "connecting" | "live" | "ended" | "error";

export interface LiveScene {
  status: LiveStatus;
  error: string | null;
  captions: Caption[];
  npcSpeaking: boolean;
  learnerSpeaking: boolean;
  openMic: boolean;
  connect(ticket: LiveTicket): Promise<void>;
  setOpenMic(open: boolean): Promise<void>;
  talk(pressed: boolean): Promise<void>;
  leave(): Promise<void>;
}

const AGENT = "lingard-npc";

export function useLiveScene(): LiveScene {
  const room = useRef<Room | null>(null);
  const [status, setStatus] = useState<LiveStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [captions, setCaptions] = useState<Caption[]>([]);
  const [npcSpeaking, setNpcSpeaking] = useState(false);
  const [learnerSpeaking, setLearnerSpeaking] = useState(false);
  const [openMic, setOpenMicState] = useState(true);

  const leave = useCallback(async () => {
    await room.current?.disconnect();
    room.current = null;
    if (Platform.OS !== "web") {
      const { AudioSession } = await import("@livekit/react-native");
      await AudioSession.stopAudioSession();
    }
    setStatus("ended");
  }, []);

  useEffect(() => () => void room.current?.disconnect(), []);

  const connect = useCallback(async (ticket: LiveTicket) => {
    setStatus("connecting");
    setError(null);
    try {
      if (Platform.OS !== "web") {
        const { AudioSession } = await import("@livekit/react-native");
        await AudioSession.startAudioSession();
      }
      const next = new Room({
        adaptiveStream: false,
        audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      next.on(RoomEvent.DataReceived, (payload: Uint8Array) => {
        const caption = parseCaption(payload);
        if (caption) setCaptions((log) => appendCaption(log, caption));
      });
      next.on(RoomEvent.ActiveSpeakersChanged, (speakers: Participant[]) => {
        const npc = speakers.some((s) => s.identity === AGENT);
        const me = speakers.some((s) => s.identity === next.localParticipant.identity);
        setNpcSpeaking((was) => {
          if (was !== npc) void Haptics.selectionAsync();
          return npc;
        });
        setLearnerSpeaking((was) => {
          if (!was && me) void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
          return me;
        });
      });
      next.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
        if (Platform.OS === "web" && track.kind === Track.Kind.Audio) document.body.appendChild(track.attach());
      });
      next.on(RoomEvent.Disconnected, () => setStatus("ended"));
      await next.connect(ticket.livekit_url, ticket.token);
      await next.localParticipant.setMicrophoneEnabled(true);
      room.current = next;
      setStatus("live");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("error");
    }
  }, []);

  const setOpenMic = useCallback(async (open: boolean) => {
    setOpenMicState(open);
    await room.current?.localParticipant.setMicrophoneEnabled(open);
  }, []);

  const talk = useCallback(
    async (pressed: boolean) => {
      if (!openMic) await room.current?.localParticipant.setMicrophoneEnabled(pressed);
    },
    [openMic],
  );

  return { status, error, captions, npcSpeaking, learnerSpeaking, openMic, connect, setOpenMic, talk, leave };
}
