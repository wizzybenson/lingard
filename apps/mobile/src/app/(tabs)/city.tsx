import { router, useFocusEffect } from "expo-router";
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWindowDimensions, View } from "react-native";

import type { CityEntry, SessionView, Today, WorldView } from "@/api/types";
import { TodayCard } from "@/home/TodayCard";
import { refreshReminderText, reminderText } from "@/state/reminders";
import { useApi } from "@/state/auth";
import { useCities } from "@/state/cities";
import { useResource } from "@/state/resource";
import { Body, Button, Card, ErrorText, Loading, Screen, Title } from "@/ui/kit";
import { MAX_WIDTH, space } from "@/ui/theme";
import { npcsAt, unlockedLocations } from "@/world/model";
import type { Location } from "@/world/types";

const POLL_MS = 2500;
const PLAN_TIMEOUT_MS = 3 * 60 * 1000; // a day plan normally takes well under a minute
// Loaded on first render, after the root layout has initialised Skia (CanvasKit on the web).
const CityCanvas = lazy(() => import("@/world/renderer/CityCanvas").then((m) => ({ default: m.CityCanvas })));
const LocationArt = lazy(() => import("@/world/renderer/LocationArt").then((m) => ({ default: m.LocationArt })));

export default function City() {
  const { t } = useTranslation();
  const api = useApi();
  const { width } = useWindowDimensions();
  const cities = useCities();
  const [chosen, setCity] = useState<CityEntry["city"] | null>(null);
  const city = chosen ?? cities.data?.[0]?.city ?? null;
  const [selected, setSelected] = useState<Location | null>(null);
  const [planning, setPlanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const today = useResource(() => api.get<Today>("/v1/today"), [api]);
  // Coming back from a goal, a lesson or a scene must show the updated streak and next step.
  useFocusEffect(today.reload);
  useEffect(() => {
    if (!today.data) return;
    const { title, body } = reminderText(t, today.data);
    void refreshReminderText(title, body).catch(() => undefined);
  }, [today.data, t]);
  const world = useResource(() => (city ? api.get<WorldView>(`/v1/world/${city}`) : Promise.resolve(null)), [city]);
  // Plan today's story ahead, so "Start" opens it at once. The server reuses a day that is still planning or not
  // played yet, so this never plans twice; it stops once the learner has practised today.
  const plannedAhead = useRef<string | null>(null);
  useEffect(() => {
    const next = today.data;
    if (!city || !next || next.next_step !== "story" || next.practised_today || plannedAhead.current === city) return;
    plannedAhead.current = city;
    void api.post<SessionView>("/v1/sessions", { city }).catch(() => (plannedAhead.current = null));
  }, [api, city, today.data]);
  // The content column is at most MAX_WIDTH wide with space(2) padding; the card inside adds another space(2).
  const column = Math.min(width, MAX_WIDTH) - space(4);
  // A stable size object: the map rebuilds its skyline paths whenever this changes.
  const mapSize = useMemo(() => ({ width: column, height: 340 }), [column]);

  const starting = useRef(false); // a double tap must not plan two days
  const startDay = async () => {
    if (starting.current) return;
    starting.current = true;
    setPlanning(true);
    setError(null);
    try {
      let session = await api.post<SessionView>("/v1/sessions", { city });
      const deadline = Date.now() + PLAN_TIMEOUT_MS;
      while (session.status === "planning") {
        if (Date.now() > deadline) throw new Error(t("city.planningTimeout"));
        await new Promise((r) => setTimeout(r, POLL_MS));
        session = await api.get<SessionView>(`/v1/sessions/${session.id}`);
      }
      if (session.status === "failed") throw new Error(t("city.planningFailed", { reason: session.error ?? "" }));
      const first = session.scene_ids[0];
      if (first) router.push({ pathname: "/scene/[id]", params: { id: first, session: session.id } });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      starting.current = false;
      setPlanning(false);
    }
  };

  return (
    <Screen
      onRefresh={() => {
        today.reload();
        world.reload();
      }}
    >
      {today.data && <TodayCard today={today.data} busy={planning} onStartStory={() => void startDay()} />}
      <ErrorText message={error} onRetry={() => void startDay()} />
      <Title>{t("city.choose")}</Title>
      <View style={{ flexDirection: "row", gap: 8 }}>
        {cities.data?.map((c) => (
          <View key={c.city} style={{ flex: 1 }}>
            <Button label={c.name} kind={c.city === city ? "primary" : "secondary"} onPress={() => setCity(c.city)} />
          </View>
        ))}
      </View>
      {world.loading && <Loading />}
      <ErrorText message={cities.error ?? world.error ?? today.error} onRetry={() => (today.error ? today.reload() : world.reload())} />
      {world.data && (
        <Suspense fallback={<Loading />}>
          <CityCanvas view={world.data} size={mapSize} onSelect={setSelected} />
        </Suspense>
      )}
      {world.data &&
        unlockedLocations(world.data).map((location) => (
          <Button
            key={location.key}
            label={`${location.name}${npcsAt(world.data!, location.key).length ? " · " + npcsAt(world.data!, location.key).map((n) => n.name.split(" ")[0]).join(", ") : ""}`}
            kind={selected?.key === location.key ? "primary" : "secondary"}
            onPress={() => setSelected(location)}
          />
        ))}
      {selected && world.data && (
        <Card>
          {selected.layer_art && selected.layer_art.length > 0 && (
            <Suspense fallback={null}>
              <LocationArt api={api} layers={selected.layer_art} width={column - space(4)} />
            </Suspense>
          )}
          <Title>{selected.name}</Title>
          <Body>{selected.description}</Body>
          <Body muted>{npcsAt(world.data, selected.key).map((n) => n.name).join(", ") || t("city.nobodyHere")}</Body>
        </Card>
      )}
      {world.data?.districts
        .filter((d) => !d.unlocked)
        .map((d) => (
          <Body key={d.key} muted>
            {d.name}: {t("city.locked", { band: d.min_band })}
          </Body>
        ))}
      {/* The Today card already carries the start button; this is only for when it couldn't load. */}
      {!today.data && !today.loading && (
        <Button label={planning ? t("city.planning") : t("city.startDay")} busy={planning} onPress={() => void startDay()} />
      )}
    </Screen>
  );
}
