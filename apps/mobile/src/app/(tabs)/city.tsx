import { router } from "expo-router";
import { lazy, Suspense, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWindowDimensions, View } from "react-native";

import type { CityEntry, SessionView, WorldView } from "@/api/types";
import { useApi } from "@/state/auth";
import { useCities } from "@/state/cities";
import { useResource } from "@/state/resource";
import { Body, Button, Card, ErrorText, Loading, Screen, Title } from "@/ui/kit";
import { npcsAt, unlockedLocations } from "@/world/model";
import type { Location } from "@/world/types";

const POLL_MS = 2500;
// Loaded on first render, after the root layout has initialised Skia (CanvasKit on the web).
const CityCanvas = lazy(() => import("@/world/renderer/CityCanvas").then((m) => ({ default: m.CityCanvas })));

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
  const world = useResource(() => (city ? api.get<WorldView>(`/v1/world/${city}`) : Promise.resolve(null)), [city]);

  const startDay = async () => {
    setPlanning(true);
    setError(null);
    try {
      let session = await api.post<SessionView>("/v1/sessions", { city });
      while (session.status === "planning") {
        await new Promise((r) => setTimeout(r, POLL_MS));
        session = await api.get<SessionView>(`/v1/sessions/${session.id}`);
      }
      const first = session.scene_ids[0];
      if (first) router.push({ pathname: "/scene/[id]", params: { id: first, session: session.id } });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPlanning(false);
    }
  };

  return (
    <Screen>
      <Title>{t("city.choose")}</Title>
      <View style={{ flexDirection: "row", gap: 8 }}>
        {cities.data?.map((c) => (
          <View key={c.city} style={{ flex: 1 }}>
            <Button label={c.name} kind={c.city === city ? "primary" : "secondary"} onPress={() => setCity(c.city)} />
          </View>
        ))}
      </View>
      {world.loading && <Loading />}
      <ErrorText message={cities.error ?? world.error ?? error} />
      {world.data && (
        <Suspense fallback={<Loading />}>
          <CityCanvas view={world.data} size={{ width: Math.min(width, 760) - 32, height: 340 }} onSelect={setSelected} />
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
      <Button label={planning ? t("city.planning") : t("city.startDay")} busy={planning} onPress={() => void startDay()} />
    </Screen>
  );
}
