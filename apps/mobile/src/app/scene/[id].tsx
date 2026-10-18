import { router, useLocalSearchParams } from "expo-router";
import { lazy, Suspense, useState } from "react";
import { useTranslation } from "react-i18next";
import { ActivityIndicator, Pressable, Switch, Text, useWindowDimensions, View } from "react-native";

import type { LiveTicket, SceneView, SessionView } from "@/api/types";
import { captionOpacity } from "@/live/captions";
import { useLiveScene, type LiveError } from "@/live/useLiveScene";
import { useApi } from "@/state/auth";
import { useResource } from "@/state/resource";
import { Body, Button, Card, ErrorText, goBack, Loading, Screen, Title } from "@/ui/kit";
import { colors, MAX_WIDTH, space } from "@/ui/theme";

// Loaded lazily: on the web, Skia modules must not be evaluated before CanvasKit has loaded (see _layout.tsx).
const LocationArt = lazy(() => import("@/world/renderer/LocationArt").then((m) => ({ default: m.LocationArt })));

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", minHeight: 44 }}>
      <Body>{label}</Body>
      <Switch value={value} onValueChange={onChange} accessibilityLabel={label} trackColor={{ true: colors.accent }} />
    </View>
  );
}

export default function Scene() {
  const { t } = useTranslation();
  const api = useApi();
  const { id, session } = useLocalSearchParams<{ id: string; session?: string }>();
  const scene = useResource(() => api.get<SceneView>(`/v1/scenes/${id}`), [id]);
  const live = useLiveScene();
  const [headphonesOk, setHeadphonesOk] = useState(false);
  const [showCaptions, setShowCaptions] = useState(true);
  const [moving, setMoving] = useState(false);
  const [moveError, setMoveError] = useState<string | null>(null);
  const { width } = useWindowDimensions();
  const band = scene.data?.learner_band ?? 4; // unknown band: keep captions fully visible

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
      const view = await api.get<SessionView>(`/v1/sessions/${session}`);
      const following = view.scene_ids[view.scene_ids.indexOf(id) + 1];
      if (following) router.replace({ pathname: "/scene/[id]", params: { id: following, session } });
      else {
        await api.post(`/v1/sessions/${session}/end`);
        router.replace({ pathname: "/notebook/[id]", params: { id: session } });
      }
    } catch (e) {
      setMoveError(e instanceof Error ? e.message : String(e));
    } finally {
      setMoving(false);
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
  return (
    <Screen back onBack={back}>
      <ErrorText message={scene.error} onRetry={scene.reload} />
      {scene.data && (
        <Card>
          {scene.data.layer_art.length > 0 && (
            <Suspense fallback={null}>
              <LocationArt api={api} layers={scene.data.layer_art} width={Math.min(width, MAX_WIDTH) - space(8)} />
            </Suspense>
          )}
          <Title>{scene.data.location_name}</Title>
          {scene.data.npc_name ? <Body muted>{t("scene.with", { name: scene.data.npc_name, role: scene.data.npc_role })}</Body> : null}
          <Body muted>{t("scene.goal")}</Body>
          <Body>{scene.data.learner_goal}</Body>
        </Card>
      )}
      {scene.data && live.status === "idle" && !headphonesOk && (
        <Card>
          <Body>{t("scene.headphones")}</Body>
          <Button label={t("app.continue")} onPress={() => setHeadphonesOk(true)} />
        </Card>
      )}
      {scene.data && live.status === "idle" && headphonesOk && <Button label={t("scene.connect")} onPress={() => void start()} />}
      {live.status === "connecting" && (
        <View style={{ flexDirection: "row", alignItems: "center", gap: space(1) }} accessibilityLiveRegion="polite">
          <ActivityIndicator color={colors.accent} />
          <Body>{t("scene.connecting")}</Body>
        </View>
      )}
      {live.status === "error" && (
        <Card>
          <ErrorText message={describe(live.error)} />
          <Button label={t("app.retry")} onPress={() => void start()} />
          <Button label={t("app.back")} kind="secondary" onPress={back} />
        </Card>
      )}
      {live.status === "live" && (
        <>
          <Body muted>{live.npcSpeaking ? t("scene.speaking") : live.learnerSpeaking ? t("scene.listening") : " "}</Body>
          <Card>
            <Toggle label={t("scene.openMic")} value={live.openMic} onChange={(v) => void live.setOpenMic(v)} />
            <Toggle label={t("scene.captions")} value={showCaptions} onChange={setShowCaptions} />
          </Card>
          {showCaptions && live.captions.length > 0 && (
            <Card>
              {live.captions.map((c) => (
                <Text
                  key={`${c.at}-${c.text}`}
                  style={{ fontSize: 17, lineHeight: 24, color: c.speaker === "npc" ? colors.ink : colors.accent, opacity: Math.max(0.35, captionOpacity(band)) }}
                >
                  {c.speaker === "npc" ? "— " : "› "}
                  {c.text}
                </Text>
              ))}
            </Card>
          )}
          {!live.openMic && (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={t("scene.pushToTalk")}
              onPressIn={() => void live.talk(true)}
              onPressOut={() => void live.talk(false)}
              style={({ pressed }) => ({
                minHeight: 96,
                borderRadius: 48,
                backgroundColor: colors.accent,
                opacity: pressed ? 0.85 : 1,
                transform: [{ scale: pressed ? 0.97 : 1 }],
                alignItems: "center",
                justifyContent: "center",
              })}
            >
              <Text style={{ color: colors.accentInk, fontSize: 18, fontWeight: "600" }}>{t("scene.pushToTalk")}</Text>
            </Pressable>
          )}
          {live.openMic && <Button label={t("scene.pause")} kind="secondary" onPress={() => void live.setOpenMic(false)} />}
          <Button label={t("scene.end")} kind="secondary" busy={moving} onPress={() => void next()} />
        </>
      )}
      {live.status === "ended" && (
        <Card>
          <Body>{t("scene.ended")}</Body>
          <Button label={t("app.continue")} busy={moving} onPress={() => void next()} />
        </Card>
      )}
      <ErrorText message={moveError} onRetry={() => void next()} />
    </Screen>
  );
}
