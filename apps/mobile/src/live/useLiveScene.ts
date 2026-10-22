/** Join a scene's LiveKit room: echo-cancelled mic, NPC audio, captions, turn haptics, open mic or push-to-talk.
 *
 * One room at a time: a second connect while one is in flight is ignored, and the room is tracked from the moment it
 * exists, so leaving the screen always disconnects it. Two joins with the same identity evict each other forever. */
import * as Haptics from "expo-haptics";
import { DisconnectReason, Room, RoomEvent, type Participant, type RemoteTrack, Track } from "livekit-client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Platform } from "react-native";

import type { LiveTicket } from "@/api/types";
import { DEV_HOST, reachable } from "@/config";
import { appendCaption, parseCaption, type Caption } from "./captions";

export type LiveStatus = "idle" | "connecting" | "live" | "ended" | "error";

/** Why a scene could not start or stopped early; the screen turns the code into words. */
export interface LiveError {
  code: "timeout" | "replaced" | "failed";
  detail?: string;
}

export interface LiveScene {
  status: LiveStatus;
  error: LiveError | null;
  captions: Caption[];
  npcSpeaking: boolean;
  learnerSpeaking: boolean;
  openMic: boolean;
  /** Fetch a ticket and join. The ticket is requested inside, so the screen shows "connecting" at once. */
  connect(ticket: () => Promise<LiveTicket>): Promise<void>;
  setOpenMic(open: boolean): Promise<void>;
  talk(pressed: boolean): Promise<void>;
  leave(): Promise<void>;
}

const AGENT = "lingard-npc";
/** Phones run an audio session around the room; the browser manages its own audio. */
const NATIVE_AUDIO = Platform.OS !== "web";
const JOIN_TIMEOUT_MS = 20_000;

class JoinTimeout extends Error {}

function within<T>(work: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new JoinTimeout()), ms);
  });
  return Promise.race([work, deadline]).finally(() => clearTimeout(timer));
}

export function useLiveScene(): LiveScene {
  const room = useRef<Room | null>(null);
  const joining = useRef(false);
  const audio = useRef<HTMLMediaElement[]>([]);
  const [status, setStatus] = useState<LiveStatus>("idle");
  const [error, setError] = useState<LiveError | null>(null);
  const [captions, setCaptions] = useState<Caption[]>([]);
  const [npcSpeaking, setNpcSpeaking] = useState(false);
  const [learnerSpeaking, setLearnerSpeaking] = useState(false);
  const [openMic, setOpenMicState] = useState(true);

  const close = useCallback(async () => {
    const current = room.current;
    room.current = null;
    for (const element of audio.current) element.remove();
    audio.current = [];
    await current?.disconnect();
    if (NATIVE_AUDIO) {
      const { AudioSession } = await import("@livekit/react-native");
      await AudioSession.stopAudioSession();
    }
  }, []);

  /** A conversation that took place is over; leaving one that never began leaves nothing to judge. */
  const leave = useCallback(async () => {
    await close();
    setStatus((s) => (s === "live" || s === "connecting" ? "ended" : s));
  }, [close]);

  useEffect(() => () => void close(), [close]);

  const connect = useCallback(
    async (ticket: () => Promise<LiveTicket>) => {
      if (joining.current || room.current) return;
      joining.current = true;
      setStatus("connecting");
      setError(null);
      try {
        const { livekit_url, token } = await ticket();
        if (NATIVE_AUDIO) {
          const { AudioSession } = await import("@livekit/react-native");
          await AudioSession.startAudioSession();
        }
        const next = new Room({
          adaptiveStream: false,
          audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
        room.current = next;
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
          if (Platform.OS === "web" && track.kind === Track.Kind.Audio) {
            const element = track.attach();
            audio.current.push(element);
            document.body.appendChild(element);
          }
        });
        next.on(RoomEvent.Disconnected, (reason?: DisconnectReason) => {
          if (room.current !== next) return; // we left on purpose
          room.current = null;
          if (reason === DisconnectReason.DUPLICATE_IDENTITY) {
            setError({ code: "replaced" });
            setStatus("error");
          } else setStatus("ended");
        });
        await within(
          (async () => {
            await next.connect(reachable(livekit_url, DEV_HOST), token);
            await next.localParticipant.setMicrophoneEnabled(true);
          })(),
          JOIN_TIMEOUT_MS,
        );
        if (room.current === next) setStatus("live");
      } catch (e) {
        await close();
        setError(e instanceof JoinTimeout ? { code: "timeout" } : { code: "failed", detail: e instanceof Error ? e.message : String(e) });
        setStatus("error");
      } finally {
        joining.current = false;
      }
    },
    [close],
  );

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
