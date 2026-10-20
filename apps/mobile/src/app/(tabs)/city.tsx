import { router, useFocusEffect } from "expo-router";
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Text, useWindowDimensions, View } from "react-native";

import type { CityEntry, KeyPoint, Profile, SessionView, Today, WorldView } from "@/api/types";
import { KeyPointStrip } from "@/school/KeyPointStrip";
import { TodayCard } from "@/home/TodayCard";
import { refreshReminderText, reminderText } from "@/state/reminders";
import { useApi } from "@/state/auth";
import { useCities } from "@/state/cities";
import { useResource } from "@/state/resource";
import { Avatar, Body, Button, Card, ErrorText, IconBubble, ListRow, Loading, Screen, Section, Segmented, Title } from "@/ui/kit";
import { colors, MAX_WIDTH, radius, shadow, space, type } from "@/ui/theme";
import { placeIcon } from "@/world/icons";
import { npcsAt, unlockedLocations } from "@/world/model";
import type { Location } from "@/world/types";

const POLL_MS = 2500;
const PLAN_TIMEOUT_MS = 3 * 60 * 1000; // a day plan normally takes well under a minute
// Loaded on first render, after the root layout has initialised Skia (CanvasKit on the web).
const CityCanvas = lazy(() => import("@/world/renderer/CityCanvas").then((m) => ({ default: m.CityCanvas })));
const LocationArt = lazy(() => import("@/world/renderer/LocationArt").then((m) => ({ default: m.LocationArt })));

/** Up to three faces, overlapping, for the people at a place. */
function Faces({ names }: { names: string[] }) {
  return (
    <View style={{ flexDirection: "row" }}>
      {names.slice(0, 3).map((name, i) => (
        <View key={name} style={{ marginLeft: i ? -10 : 0, borderWidth: 2, borderColor: colors.card, borderRadius: 18 }}>
          <Avatar name={name} size={30} />
        </View>
      ))}
    </View>
  );
}

export default function City() {
  const { t } = useTranslation();
  const api = useApi();
  const { width } = useWindowDimensions();
  const cities = useCities();
  const [chosen, setCity] = useState<CityEntry["city"] | null>(null);
  const city = chosen ?? cities.data?.[0]?.city ?? null;
  const cityLanguage = cities.data?.find((c) => c.city === city)?.language ?? null;
  const [selected, setSelected] = useState<Location | null>(null);
  const placeKind = selected?.kind ?? null;
  const useful = useResource(
    () => (placeKind && cityLanguage ? api.get<KeyPoint[]>(`/v1/key-points/for-place?language=${cityLanguage}&place=${placeKind}`) : Promise.resolve(null)),
    [api, placeKind, cityLanguage],
  );
  const [planning, setPlanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const today = useResource(() => api.get<Today>("/v1/today"), [api]);
  const profile = useResource(() => api.get<Profile>("/v1/me"), [api]);
  // Coming back from a goal, a lesson or a scene must show the updated streak and next step.
  useFocusEffect(today.reload);
  useEffect(() => {
    if (!today.data) return;
    const { title, body } = reminderText(t, today.data);
    void refreshReminderText(title, body).catch(() => undefined);
  }, [today.data, t]);
  const world = useResource(() => (city ? api.get<WorldView>(`/v1/world/${city}`) : Promise.resolve(null)), [city]);
  // Coming back from a finished day must show the next day's number.
  useFocusEffect(world.reload);
  const day = world.data && world.data.city === city ? (world.data.days_lived ?? 0) + 1 : null;
  // Plan the next story day ahead, so "Begin" opens it at once. The server reuses a day that is still planning or
  // not played yet, so this never plans twice. It follows progress (the day number), never the calendar.
  const plannedAhead = useRef<string | null>(null);
  useEffect(() => {
    const key = `${city}:${day}`;
    if (!city || !day || today.data?.next_step !== "story" || plannedAhead.current === key) return;
    plannedAhead.current = key;
    void api.post<SessionView>("/v1/sessions", { city }).catch(() => (plannedAhead.current = null));
  }, [api, city, day, today.data?.next_step]);
  // The content column is at most MAX_WIDTH wide with space(2.5) padding on each side.
  const column = Math.min(width, MAX_WIDTH) - space(5);
  // A stable size object: the map rebuilds its skyline paths whenever this changes.
  const mapSize = useMemo(() => ({ width: column, height: 300 }), [column]);

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

  const name = profile.data?.display_name.split(" ")[0];
  const places = world.data ? unlockedLocations(world.data) : [];
  const locked = world.data?.districts.filter((d) => !d.unlocked) ?? [];

  return (
    <Screen
      eyebrow={day && world.data ? t("city.dayIn", { day, city: world.data.name }) : undefined}
      title={name ? t("city.greeting", { name }) : t("tabs.city")}
      onRefresh={() => {
        today.reload();
        world.reload();
      }}
    >
      {today.data && <TodayCard
          today={today.data}
          day={day}
          busy={planning} onStartStory={() => void startDay()} />}
      <ErrorText message={error} onRetry={() => void startDay()} />
      {/* The Today card carries the start button; this is only for when it couldn't load. */}
      {!today.data && !today.loading && (
        <Button label={planning ? t("city.planning") : t("city.startDay")} icon="play" busy={planning} onPress={() => void startDay()} />
      )}

      <View style={{ gap: space(1.5), marginTop: space(1) }}>
        <Title>{t("city.choose")}</Title>
        {cities.data && cities.data.length > 1 && (
          <Segmented options={cities.data.map((c) => ({ value: c.city, label: c.name }))} value={city} onChange={setCity} />
        )}
      </View>
      {world.loading && !world.data && <Loading />}
      <ErrorText message={cities.error ?? world.error ?? today.error} onRetry={() => (today.error ? today.reload() : world.reload())} />
      {world.data && (
        <View style={[{ borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.card }, shadow(2)]}>
          <Suspense fallback={<View style={{ height: mapSize.height }} />}>
            <CityCanvas view={world.data} size={mapSize} onSelect={setSelected} />
          </Suspense>
        </View>
      )}
      {selected && world.data && (
        <Card style={{ padding: 0, overflow: "hidden" }}>
          {selected.layer_art && selected.layer_art.length > 0 && (
            <Suspense fallback={null}>
              <LocationArt api={api} layers={selected.layer_art} width={column} />
            </Suspense>
          )}
          <View style={{ padding: space(2.5), gap: space(1) }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: space(1.5) }}>
              <IconBubble name={placeIcon(selected)} tone="accent" />
              <View style={{ flex: 1 }}>
                <Title>{selected.name}</Title>
              </View>
            </View>
            <Body>{selected.description}</Body>
            <Text style={[type.overline, { marginTop: space(1) }]}>{t("city.peopleHere")}</Text>
            {npcsAt(world.data, selected.key).length === 0 ? (
              <Body muted>{t("city.nobodyHere")}</Body>
            ) : (
              npcsAt(world.data, selected.key).map((npc) => (
                <View key={npc.key} style={{ flexDirection: "row", alignItems: "center", gap: space(1.5) }}>
                  <Avatar name={npc.name} size={36} />
                  <View style={{ flex: 1 }}>
                    <Text style={type.headline}>{npc.name}</Text>
                    <Text style={type.caption}>{npc.role}</Text>
                  </View>
                </View>
              ))
            )}
          </View>
        </Card>
      )}
      {selected && placeKind && <KeyPointStrip key={selected.key} id={`place.${placeKind}`} eyebrow={t("journey.usefulHere")} points={useful.data} />}
      {world.data && places.length > 0 && (
        <Section title={t("city.places")}>
          {places.map((location) => {
            const people = npcsAt(world.data!, location.key);
            return (
              <ListRow
                key={location.key}
                icon={placeIcon(location)}
                title={location.name}
                subtitle={people.map((n) => n.name).join(", ") || t("city.nobodyHere")}
                selected={selected?.key === location.key}
                trailing={people.length ? <Faces names={people.map((n) => n.name)} /> : undefined}
                onPress={() => setSelected(location)}
              />
            );
          })}
        </Section>
      )}
      {locked.length > 0 && (
        <Section title={t("city.lockedTitle")}>
          {locked.map((d) => (
            <ListRow key={d.key} icon="lock-closed" title={d.name} subtitle={t("city.locked", { band: d.min_band })} disabled />
          ))}
        </Section>
      )}
    </Screen>
  );
}
