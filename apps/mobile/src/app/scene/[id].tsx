import { router, useLocalSearchParams } from "expo-router";
import { lazy, Suspense, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, Switch, Text, useWindowDimensions, View } from "react-native";

import type { LiveTicket, SceneView, SessionView } from "@/api/types";
import { captionOpacity } from "@/live/captions";
import { useLiveScene } from "@/live/useLiveScene";
import { useApi } from "@/state/auth";
import { useResource } from "@/state/resource";
import { Body, Button, Card, ErrorText, Loading, Screen, Title } from "@/ui/kit";
import { colors } from "@/ui/theme";

// Loaded lazily: on the web, Skia modules must not be evaluated before CanvasKit has loaded (see _layout.tsx).
const LocationArt = lazy(() => import("@/world/renderer/LocationArt").then((m) => ({ default: m.LocationArt })));

export default function Scene() {
  const { t } = useTranslation();
  const api = useApi();
  const { id, session } = useLocalSearchParams<{ id: string; session?: string }>();
  const scene = useResource(() => api.get<SceneView>(`/v1/scenes/${id}`), [id]);
  const live = useLiveScene();
  const [headphonesOk, setHeadphonesOk] = useState(false);
  const [showCaptions, setShowCaptions] = useState(true);
  const { width } = useWindowDimensions();
  const band = scene.data?.learner_band ?? 4; // unknown band: keep captions fully visible

  const start = async () => {
    const ticket = await api.post<LiveTicket>(`/v1/scenes/${id}/live`);
    await live.connect(ticket);
  };

  const next = async () => {
    await live.leave();
    if (!session) return router.back();
    const view = await api.get<SessionView>(`/v1/sessions/${session}`);
    const index = view.scene_ids.indexOf(id);
    const following = view.scene_ids[index + 1];
    if (following) router.replace({ pathname: "/scene/[id]", params: { id: following, session } });
    else {
      await api.post(`/v1/sessions/${session}/end`);
      router.replace({ pathname: "/notebook/[id]", params: { id: session } });
    }
  };

  if (scene.loading) return <Screen><Loading /></Screen>;
  return (
    <Screen>
      <ErrorText message={scene.error ?? live.error} />
      {scene.data && (
        <Card>
          {scene.data.layer_art.length > 0 && (
            <Suspense fallback={null}>
              <LocationArt api={api} layers={scene.data.layer_art} width={Math.min(width, 760) - 64} />
            </Suspense>
          )}
          <Title>{scene.data.location_name}</Title>
          {scene.data.npc_name ? <Body muted>{t("scene.with", { name: scene.data.npc_name, role: scene.data.npc_role })}</Body> : null}
          <Body muted>{t("scene.goal")}</Body>
          <Body>{scene.data.learner_goal}</Body>
        </Card>
      )}
      {live.status === "idle" && !headphonesOk && (
        <Card>
          <Body>{t("scene.headphones")}</Body>
          <Button label={t("app.continue")} onPress={() => setHeadphonesOk(true)} />
        </Card>
      )}
      {live.status === "idle" && headphonesOk && <Button label={t("scene.connect")} onPress={() => void start()} />}
      {live.status === "connecting" && <Body>{t("scene.connecting")}</Body>}
      {live.status === "live" && (
        <>
          <Body muted>{live.npcSpeaking ? t("scene.speaking") : live.learnerSpeaking ? t("scene.listening") : " "}</Body>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Switch value={live.openMic} onValueChange={(v) => void live.setOpenMic(v)} accessibilityLabel={t("scene.openMic")} />
            <Body>{t("scene.openMic")}</Body>
            <Switch value={showCaptions} onValueChange={setShowCaptions} accessibilityLabel={t("scene.captions")} />
            <Body>{t("scene.captions")}</Body>
          </View>
          {showCaptions && (
            <Card>
              {live.captions.map((c) => (
                <Text
                  key={`${c.at}-${c.text}`}
                  style={{ fontSize: 17, color: c.speaker === "npc" ? colors.ink : colors.accent, opacity: Math.max(0.35, captionOpacity(band)) }}
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
              style={{ minHeight: 96, borderRadius: 48, backgroundColor: colors.accent, alignItems: "center", justifyContent: "center" }}
            >
              <Text style={{ color: colors.accentInk, fontSize: 18 }}>{t("scene.pushToTalk")}</Text>
            </Pressable>
          )}
          <Button label={t("scene.pause")} kind="secondary" onPress={() => void live.setOpenMic(false)} />
          <Button label={t("scene.end")} kind="secondary" onPress={() => void next()} />
        </>
      )}
      {live.status === "ended" && <Button label={t("app.continue")} onPress={() => void next()} />}
    </Screen>
  );
}
