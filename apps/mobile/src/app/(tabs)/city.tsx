import { router, useFocusEffect } from "expo-router";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Text, useWindowDimensions, View } from "react-native";

import type { KeyPoint, Profile, SessionView, Today, WorldView } from "@/api/types";
import { KeyPointStrip } from "@/school/KeyPointStrip";
import { ExamLine, Stats, TodayCard } from "@/home/TodayCard";
import { TodayPath } from "@/home/TodayPath";
import { refreshReminderText, reminderText } from "@/state/reminders";
import { useApi } from "@/state/auth";
import { useFocus } from "@/state/focus";
import { useResource } from "@/state/resource";
import { Avatar, Body, Button, Card, Caption, Disclosure, ErrorText, IconBubble, ListRow, Loading, Screen, Section, Title } from "@/ui/kit";
import { FocusSwitch } from "@/ui/FocusSwitch";
import { colors, MAX_WIDTH, radius, shadow, space, type } from "@/ui/theme";
import { placeIcon } from "@/world/icons";
import { npcsAt, unlockedLocations } from "@/world/model";
import type { Location } from "@/world/types";

const POLL_MS = 2500;
const COACH_POLL_MS = 4000;
const COACH_LOOKS = 8;
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
  const focus = useFocus();
  const city = focus.city?.city ?? null;
  const cityLanguage = focus.language;
  const [selected, setSelected] = useState<Location | null>(null);
  const placeKind = selected?.kind ?? null;
  const useful = useResource(
    () => (placeKind && cityLanguage ? api.get<KeyPoint[]>(`/v1/key-points/for-place?language=${cityLanguage}&place=${placeKind}`) : Promise.resolve(null)),
    [api, placeKind, cityLanguage],
  );
  const [planning, setPlanning] = useState(false);
  const [ahead, setAhead] = useState<SessionView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const today = useResource(() => api.get<Today>("/v1/today"), [api]);
  // The coach tailors the day in the background: look again shortly, and the path updates in place. A few looks at
  // most: if it is slow or failing, the path from the curriculum's order simply stays.
  const thinking = today.data?.coach === "thinking";
  const { reload: reloadToday } = today;
  const coachLooks = useRef(0);
  useEffect(() => {
    if (!thinking || coachLooks.current >= COACH_LOOKS) return;
    const timer = setTimeout(() => {
      coachLooks.current += 1;
      reloadToday();
    }, COACH_POLL_MS);
    return () => clearTimeout(timer);
  }, [thinking, reloadToday, today.data]);
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
  const aheadId = ahead?.id;
  useFocusEffect(
    useCallback(() => {
      if (aheadId) void api.get<SessionView>(`/v1/sessions/${aheadId}`).then(setAhead).catch(() => undefined);
    }, [api, aheadId]),
  );
  const day = world.data && world.data.city === city ? (world.data.days_lived ?? 0) + 1 : null;
  // Plan the next story day ahead, so "Begin" opens it at once. The server reuses a day that is still planning or
  // not played yet, so this never plans twice. It follows progress (the day number), never the calendar.
  const plannedAhead = useRef<string | null>(null);
  useEffect(() => {
    const key = `${city}:${day}`;
    if (!city || !day || today.data?.next_step !== "story" || plannedAhead.current === key) return;
    plannedAhead.current = key;
    void api
      .post<SessionView>("/v1/sessions", { city })
      .then(setAhead)
      .catch(() => (plannedAhead.current = null));
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
      // A day left halfway goes on where it stopped; its later scenes may still be on their way.
      while (!session.next_scene_id && !session.complete) {
        if (Date.now() > deadline) throw new Error(t("city.planningTimeout"));
        await new Promise((r) => setTimeout(r, POLL_MS));
        session = await api.get<SessionView>(`/v1/sessions/${session.id}`);
      }
      setAhead(session);
      if (session.next_scene_id) router.push({ pathname: "/scene/[id]", params: { id: session.next_scene_id, session: session.id } });
      else {
        await api.post(`/v1/sessions/${session.id}/end`); // every scene played: the night's notebook closes the day
        router.push({ pathname: "/notebook/[id]", params: { id: session.id } });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      starting.current = false;
      setPlanning(false);
    }
  };

  const name = profile.data?.display_name.split(" ")[0];
  const places = world.data ? unlockedLocations(world.data) : [];
  const nextChapter = world.data?.districts.find((d) => !d.unlocked);
  const storyLabel = planning
    ? t("city.planning")
    : day
      ? t(ahead?.city === city && ahead.played > 0 ? "today.next.continue" : "today.next.story", { day })
      : t("city.startDay");
  const path = today.data?.path ?? [];

  return (
    <Screen
      eyebrow={day && world.data ? t("city.dayIn", { day, city: world.data.name }) : undefined}
      title={name ? t("city.greeting", { name }) : t("tabs.city")}
      accessory={today.data ? <Stats today={today.data} /> : undefined}
      onRefresh={() => {
        today.reload();
        world.reload();
      }}
    >
      {/* One guided path once the level is known; before that, the getting-started steps (decision 0029). */}
      {today.data && path.length > 0 && (
        <TodayPath stops={path} coach={today.data.coach} storyLabel={storyLabel} storyBusy={planning} onStory={() => void startDay()} />
      )}
      {today.data && path.length === 0 && today.data.next_step !== "story" && <TodayCard today={today.data} />}
      {/* Errors sit where they happened: the day's at the top with its path, the map's beside the map. */}
      <ErrorText message={error} onRetry={() => void startDay()} />
      <ErrorText message={today.error} onRetry={today.reload} />
      {/* The path carries the start button; this is only for when it couldn't load. */}
      {!today.loading && (!today.data || (path.length === 0 && today.data.next_step === "story")) && (
        <Button label={storyLabel} icon="play" busy={planning} onPress={() => void startDay()} />
      )}
      {today.data && today.data.goals.length > 0 && <ExamLine today={today.data} pack={focus.city?.pack ?? null} />}

      <View style={{ flexDirection: "row", alignItems: "center", gap: space(1), marginTop: space(1.5) }}>
        <View style={{ flex: 1 }}>
          <Title>{world.data?.name ?? t("city.choose")}</Title>
        </View>
        <FocusSwitch show="city" />
      </View>
      {world.loading && !world.data && <Loading />}
      <ErrorText message={world.error} onRetry={world.reload} />
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
        // The map already shows every place: the list is there for whoever wants it, folded.
        <Disclosure title={t("city.places")} hint={String(places.length)}>
          <Section>
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
        </Disclosure>
      )}
      {nextChapter && <Caption>{t("city.nextChapter", { name: nextChapter.name, band: nextChapter.min_band })}</Caption>}
    </Screen>
  );
}
