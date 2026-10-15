/** Goal setting: which exam, when, and the CLB/NCLC level needed per skill. Everything else is measured against it. */
import { router } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import type { Profile } from "@/api/types";
import { useApi } from "@/state/auth";
import { useCities } from "@/state/cities";
import { useResource } from "@/state/resource";
import { Body, Button, Card, ErrorText, Field, Loading, Screen, Title } from "@/ui/kit";

const SKILLS = ["listening", "reading", "writing", "speaking"] as const;
const LEVELS = [4, 5, 6, 7, 8, 9, 10];
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export default function Goal() {
  const { t } = useTranslation();
  const api = useApi();
  const cities = useCities();
  const profile = useResource(() => api.get<Profile>("/v1/me"), [api]);
  const [dates, setDates] = useState<Record<string, string>>({});
  const [targets, setTargets] = useState<Record<string, Record<string, number>>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadedFrom, setLoadedFrom] = useState<Profile | null>(null);

  // Start the form from the saved profile whenever a fresh one arrives (adjusting state during render, not in an effect).
  if (profile.data && profile.data !== loadedFrom) {
    setLoadedFrom(profile.data);
    setDates(profile.data.exam_dates);
    setTargets(profile.data.target_bands);
  }

  const save = async () => {
    const bad = Object.values(dates).find((d) => d && !ISO_DATE.test(d));
    if (bad !== undefined) return setError(t("goal.badDate"));
    setBusy(true);
    setError(null);
    try {
      const packs = cities.data?.map((c) => c.pack) ?? [];
      const examDates = Object.fromEntries(packs.map((p) => [p, dates[p] ? dates[p] : null]));
      await api.patch("/v1/me", { exam_dates: examDates, target_bands: targets });
      router.back();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!profile.data || !cities.data) return <Screen><Loading /></Screen>;
  return (
    <Screen>
      <Title>{t("goal.title")}</Title>
      <Body muted>{t("goal.intro")}</Body>
      {cities.data.map(({ pack, pack_name }) => {
        const chosen = dates[pack] !== undefined;
        return (
          <Card key={pack}>
            <Title>{pack_name}</Title>
            {!chosen ? (
              <Button label={t("goal.prepare")} kind="secondary" onPress={() => setDates((d) => ({ ...d, [pack]: "" }))} />
            ) : (
              <>
                <Field
                  label={t("goal.examDate")}
                  value={dates[pack] ?? ""}
                  onChangeText={(v) => setDates((d) => ({ ...d, [pack]: v.trim() }))}
                  placeholder="2027-03-01"
                  autoCapitalize="none"
                />
                <Body muted>{t("goal.target")}</Body>
                {SKILLS.map((skill) => (
                  <View key={skill} style={{ gap: 4 }}>
                    <Body>{t(`skills.${skill}`)}</Body>
                    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
                      {LEVELS.map((level) => (
                        <View key={level} style={{ minWidth: 48 }}>
                          <Button
                            label={String(level)}
                            kind={targets[pack]?.[skill] === level ? "primary" : "secondary"}
                            onPress={() => setTargets((all) => ({ ...all, [pack]: { ...all[pack], [skill]: level } }))}
                          />
                        </View>
                      ))}
                    </View>
                  </View>
                ))}
                <Button
                  label={t("goal.noExam")}
                  kind="secondary"
                  onPress={() => setDates(({ [pack]: _removed, ...rest }) => rest)}
                />
              </>
            )}
          </Card>
        );
      })}
      <ErrorText message={error} />
      <Button label={t("goal.save")} busy={busy} onPress={() => void save()} />
    </Screen>
  );
}
