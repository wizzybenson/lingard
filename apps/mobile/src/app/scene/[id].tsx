import * as Haptics from "expo-haptics";
import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Ionicons from "@expo/vector-icons/Ionicons";
import { ActivityIndicator, Pressable, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import Animated, { cancelAnimation, FadeInDown, useAnimatedStyle, useSharedValue, withRepeat, withTiming } from "react-native-reanimated";

import type { Debrief, KeyPoint, LiveTicket, SceneView, SessionView } from "@/api/types";
import { MissionBriefCard, MissionDebriefCard } from "@/missions/Mission";
import { KeyPointStrip } from "@/school/KeyPointStrip";
import { captionOpacity } from "@/live/captions";
import { useLiveScene, type LiveError } from "@/live/useLiveScene";
import { useApi } from "@/state/auth";
import { useResource } from "@/state/resource";
import { Avatar, Button, Card, ErrorText, goBack, Loading, Screen, Title, type IconName } from "@/ui/kit";
import { colors, fonts, MAX_WIDTH, radius, shadow, space, type } from "@/ui/theme";

const NEXT_SCENE_POLL_MS = 2000;
const NEXT_SCENE_TIMEOUT_MS = 3 * 60 * 1000;

// Loaded lazily: on the web, Skia modules must not be evaluated before CanvasKit has loaded (see _layout.tsx).
const LocationArt = lazy(() =>
  import("@/world/renderer/LocationArt").then((m) => ({
    default: m.LocationArt,
  })),
);

/** A pill that switches a setting on and off (open mic, captions). */
function PillToggle({ label, icon, value, onChange }: { label: string; icon: IconName; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityLabel={label}
      accessibilityState={{ checked: value }}
      onPress={() => onChange(!value)}
      style={[styles.pill, value ? styles.pillOn : styles.pillOff]}
    >
      <Ionicons name={icon} size={16} color={value ? colors.accentInk : colors.inkSoft} />
      <Text style={[styles.pillText, { color: value ? colors.accentInk : colors.inkSoft }]} numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
}

/** The NPC's face with a soft ring that breathes while they speak. */
function SpeakingAvatar({ name, speaking, size }: { name: string; speaking: boolean; size: number }) {
  const pulse = useSharedValue(0);
  useEffect(() => {
    if (speaking) pulse.set(withRepeat(withTiming(1, { duration: 700 }), -1, true));
    else {
      cancelAnimation(pulse);
      pulse.set(withTiming(0, { duration: 200 }));
    }
  }, [pulse, speaking]);
  const ring = useAnimatedStyle(() => ({
    opacity: 0.25 + 0.5 * pulse.value,
    transform: [{ scale: 1 + 0.12 * pulse.value }],
  }));
  return (
    <View
      style={{
        width: size,
        height: size,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Animated.View style={[StyleSheet.absoluteFill, { borderRadius: size / 2, backgroundColor: colors.sunset }, ring]} />
      <Avatar name={name} size={size - 8} />
    </View>
  );
}

export default function Scene() {
  const { t } = useTranslation();
  const api = useApi();
  const { id, session } = useLocalSearchParams<{
    id: string;
    session?: string;
  }>();
  const scene = useResource(() => api.get<SceneView>(`/v1/scenes/${id}`), [id]);
  const live = useLiveScene();
  const [showCaptions, setShowCaptions] = useState(true);
  const [moving, setMoving] = useState(false);
  const [moveError, setMoveError] = useState<string | null>(null);
  const [preparingNext, setPreparingNext] = useState(false);
  const { width } = useWindowDimensions();
  const band = scene.data?.learner_band ?? 4; // unknown band: keep captions fully visible
  // Lessons woven into the scene, never in its way: the words and phrases this conversation will use, before going
  // in, and the confirmed mistakes of this conversation once it is over (or while the next scene is prepared).
  const prep = useResource(() => api.get<KeyPoint[]>(`/v1/scenes/${id}/prep`), [api, id]);
  const over = live.status === "ended" || preparingNext;
  // The mission is judged once it is over; its debrief is the screen between this scene and the next.
  // A mock exam's speaking part has no mission: it is scored by the examiner, so it simply ends.
  const mission = scene.data?.mission ?? null;
  const judged = live.status === "ended" && mission !== null;
  const debrief = useResource(() => (judged ? api.post<Debrief>(`/v1/scenes/${id}/debrief`) : Promise.resolve(null)), [api, id, judged]);
  const brushUp = useResource(() => (over ? api.get<KeyPoint[]>(`/v1/scenes/${id}/brush-up`) : Promise.resolve(null)), [api, id, over]);
  const { reload: reloadPrep } = prep;
  const { reload: reloadBrushUp } = brushUp;
  useFocusEffect(
    useCallback(() => {
      reloadPrep(); // back from a lesson: what was just learned drops out of the offer
      reloadBrushUp();
    }, [reloadPrep, reloadBrushUp]),
  );

  const start = () => live.connect(() => api.post<LiveTicket>(`/v1/scenes/${id}/live`));

  const describe = (error: LiveError | null): string | null => {
    if (!error) return null;
    if (error.code === "failed") return t("scene.failed", { detail: error.detail ?? "" });
    return t(`scene.${error.code}`);
  };

  /** On to the next scene of the day, or the notebook when the day is done. */
  const next = async () => {
    setMoving(true);
    setMoveError(null);
    try {
      await live.leave();
      if (!session) return goBack();
      const following = await followingScene(session);
      if (following)
        router.replace({
          pathname: "/scene/[id]",
          params: { id: following, session },
        });
      else {
        await api.post(`/v1/sessions/${session}/end`);
        router.replace({ pathname: "/notebook/[id]", params: { id: session } });
      }
    } catch (e) {
      setMoveError(e instanceof Error ? e.message : String(e));
    } finally {
      setMoving(false);
      setPreparingNext(false);
    }
  };

  /** The day's next scene. Later scenes compile while the first is played, so wait for one rather than end the day. */
  const followingScene = async (sessionId: string): Promise<string | null> => {
    const deadline = Date.now() + NEXT_SCENE_TIMEOUT_MS;
    for (;;) {
      const view = await api.get<SessionView>(`/v1/sessions/${sessionId}`);
      const following = view.scene_ids[view.scene_ids.indexOf(id) + 1];
      if (following) return following;
      if (view.complete || view.status !== "ready" || Date.now() > deadline) return null;
      setPreparingNext(true);
      await new Promise((r) => setTimeout(r, NEXT_SCENE_POLL_MS));
    }
  };

  const back = () => {
    void live.leave().finally(goBack);
  };

  if (scene.loading) {
    return (
      <Screen back onBack={back}>
        <Loading />
      </Screen>
    );
  }
  const npcName = scene.data?.npc_name ?? "";
  const status = live.npcSpeaking ? t("scene.speaking") : live.learnerSpeaking ? t("scene.listening") : null;

  // Going in stays one tap away, whatever is offered above it.
  const enter = scene.data && live.status === "idle" && <Button label={t("scene.connect")} icon="mic" onPress={() => void start()} />;
  const onward = live.status === "ended" && (
    <Button
      label={t(mission ? "mission.continue" : "app.continue")}
      icon="arrow-forward"
      busy={moving}
      disabled={judged && !debrief.data && !debrief.error}
      onPress={() => void next()}
    />
  );
  // While live, talking and leaving stay pinned under the conversation instead of scrolling away as it grows.
  const controls = live.status === "live" && (
    <>
      {!live.openMic && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("scene.pushToTalk")}
          onPressIn={() => {
            void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
            void live.talk(true);
          }}
          onPressOut={() => {
            void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
            void live.talk(false);
          }}
          style={({ pressed }) => [
            styles.talk,
            shadow(2),
            pressed && {
              transform: [{ scale: 0.97 }],
              backgroundColor: colors.accentDeep,
            },
          ]}
        >
          <Ionicons name="mic" size={26} color={colors.accentInk} />
          <Text style={styles.talkText}>{t("scene.pushToTalk")}</Text>
        </Pressable>
      )}
      <View style={{ flexDirection: "row", gap: space(1) }}>
        {live.openMic && (
          <View style={{ flex: 1 }}>
            <Button label={t("scene.pause")} kind="secondary" icon="pause" onPress={() => void live.setOpenMic(false)} />
          </View>
        )}
        <View style={{ flex: 1 }}>
          <Button label={t("scene.end")} kind="tinted" icon="exit-outline" onPress={() => void live.leave()} />
        </View>
      </View>
    </>
  );

  return (
    <Screen back onBack={back} footer={controls || enter || onward || undefined} followContent={live.status === "live"}>
      <ErrorText message={scene.error} onRetry={scene.reload} />
      {scene.data && (live.status === "live" || live.status === "ended") && (
        <Card style={styles.compact}>
          {npcName ? <SpeakingAvatar name={npcName} speaking={live.npcSpeaking} size={52} /> : null}
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={type.headline} numberOfLines={1}>
              {npcName || scene.data.location_name}
            </Text>
            <View style={{ flexDirection: "row", gap: 6, alignItems: "flex-start" }}>
              <Ionicons name="flag" size={14} color={colors.accentDeep} style={{ marginTop: 2 }} />
              <Text style={[type.caption, { flex: 1, color: colors.inkSoft }]} numberOfLines={2}>
                {scene.data.learner_goal}
              </Text>
            </View>
          </View>
        </Card>
      )}
      {scene.data && live.status !== "live" && live.status !== "ended" && (
        <Card style={{ padding: 0, overflow: "hidden" }}>
          {scene.data.layer_art.length > 0 && (
            <Suspense fallback={null}>
              <LocationArt api={api} layers={scene.data.layer_art} width={Math.min(width, MAX_WIDTH) - space(5)} />
            </Suspense>
          )}
          <View style={{ padding: space(2.5), gap: space(1.5) }}>
            <Title>{scene.data.location_name}</Title>
            {npcName ? (
              <View style={styles.person}>
                <Avatar name={npcName} size={40} />
                <View style={{ flex: 1 }}>
                  <Text style={type.headline}>{npcName}</Text>
                  <Text style={type.caption}>{scene.data.npc_role}</Text>
                </View>
              </View>
            ) : null}
            <MissionBriefCard goal={scene.data.learner_goal} brief={scene.data.mission} />
          </View>
        </Card>
      )}
      {scene.data && live.status === "idle" && (
        <View style={{ gap: space(1.5) }}>
          <KeyPointStrip id={`scene.${id}.prep`} eyebrow={t("journey.beforeScene")} points={prep.data} />
          <View style={styles.tip}>
            <Ionicons name="headset" size={18} color={colors.muted} />
            <Text style={[type.callout, { flex: 1 }]}>{t("scene.headphones")}</Text>
          </View>
        </View>
      )}
      {live.status === "connecting" && (
        <Card style={{ alignItems: "center", paddingVertical: space(4) }}>
          <ActivityIndicator color={colors.accent} size="large" />
          <Text style={type.callout} accessibilityLiveRegion="polite">
            {t("scene.connecting")}
          </Text>
        </Card>
      )}
      {live.status === "error" && (
        <Card>
          <ErrorText message={describe(live.error)} />
          <Button label={t("app.retry")} icon="refresh" onPress={() => void start()} />
          <Button label={t("app.back")} kind="ghost" onPress={back} />
        </Card>
      )}
      {live.status === "live" && (
        <>
          <View style={styles.liveBar}>
            <View style={[styles.statusPill, status ? styles.statusOn : null]}>
              <View
                style={[
                  styles.statusDot,
                  {
                    backgroundColor: live.npcSpeaking ? colors.sunset : live.learnerSpeaking ? colors.success : colors.muted,
                  },
                ]}
              />
              <Text style={[type.caption, { fontFamily: fonts.semibold, color: colors.inkSoft }]} numberOfLines={1}>
                {status ?? t("scene.live")}
              </Text>
            </View>
            <View style={{ flexDirection: "row", gap: space(0.75) }}>
              <PillToggle label={t("scene.openMic")} icon="mic-outline" value={live.openMic} onChange={(v) => void live.setOpenMic(v)} />
              <PillToggle label={t("scene.captions")} icon="text" value={showCaptions} onChange={setShowCaptions} />
            </View>
          </View>
          {showCaptions && (
            <View style={{ gap: space(1) }}>
              {live.captions.map((c, i) => {
                const npc = c.speaker === "npc";
                // Like a messaging app: the face shows once, beside the last line of a run of lines.
                const lastOfRun = live.captions[i + 1]?.speaker !== c.speaker;
                return (
                  <Animated.View
                    key={`${c.speaker}-${c.at}`}
                    entering={FadeInDown.duration(220)}
                    style={[styles.bubbleRow, !npc && { justifyContent: "flex-end" }]}
                  >
                    {npc && npcName ? lastOfRun ? <Avatar name={npcName} size={28} /> : <View style={{ width: 28 }} /> : null}
                    <View
                      testID={npc ? "caption-npc" : "caption-learner"}
                      style={[styles.bubble, npc ? styles.bubbleNpc : styles.bubbleMe, { opacity: Math.max(0.35, captionOpacity(band)) }]}
                    >
                      <Text style={[type.body, !npc && { color: colors.accentInk }]}>{c.text}</Text>
                    </View>
                  </Animated.View>
                );
              })}
            </View>
          )}
        </>
      )}
      {judged && <MissionDebriefCard debrief={debrief.data} error={debrief.error} />}
      {over && <KeyPointStrip id={`scene.${id}`} eyebrow={t("journey.afterScene")} points={brushUp.data} />}
      {preparingNext && (
        <View style={styles.tip} accessibilityLiveRegion="polite">
          <ActivityIndicator color={colors.accent} />
          <Text style={[type.callout, { flex: 1 }]}>{t("scene.preparingNext")}</Text>
        </View>
      )}
      <ErrorText message={moveError} onRetry={() => void next()} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  person: { flexDirection: "row", alignItems: "center", gap: space(1.5) },
  compact: {
    flexDirection: "row",
    alignItems: "center",
    gap: space(1.5),
    paddingVertical: space(1.5),
  },
  tip: {
    flexDirection: "row",
    alignItems: "center",
    gap: space(1),
    paddingHorizontal: space(0.5),
  },
  liveBar: { gap: space(1.25) },
  statusPill: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    gap: 6,
    backgroundColor: colors.paperDeep,
    borderRadius: radius.pill,
    paddingHorizontal: space(1.25),
    paddingVertical: 6,
  },
  statusOn: { backgroundColor: colors.card },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderRadius: radius.pill,
    paddingHorizontal: space(1.5),
    minHeight: 36,
  },
  pillOn: { backgroundColor: colors.accent },
  pillOff: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
  },
  pillText: { fontFamily: fonts.semibold, fontSize: 13 },
  bubbleRow: { flexDirection: "row", alignItems: "flex-end", gap: space(1) },
  bubble: {
    maxWidth: "82%",
    borderRadius: radius.lg,
    paddingHorizontal: space(1.75),
    paddingVertical: space(1.25),
  },
  bubbleNpc: {
    backgroundColor: colors.card,
    borderBottomLeftRadius: 6,
    ...shadow(1),
  },
  bubbleMe: { backgroundColor: colors.accent, borderBottomRightRadius: 6 },
  talk: {
    minHeight: 72,
    borderRadius: radius.pill,
    backgroundColor: colors.accent,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: space(1),
  },
  talkText: {
    fontFamily: fonts.semibold,
    fontSize: 17,
    color: colors.accentInk,
  },
});
