/** Accent studio: listen to a line (in the learner's own voice once they have one), say it, see what was clear and
 * which sounds to work on. Three tries per line; the last one is reviewed on the learner's spaced schedule. */
import { router } from "expo-router";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { StyleSheet, Text, View } from "react-native";

import type { CityEntry } from "@/api/types";
import { PlayButton } from "@/live/PlayButton";
import { Recorder } from "@/live/Recorder";
import { useApi } from "@/state/auth";
import { useCities } from "@/state/cities";
import { useResource } from "@/state/resource";
import { Body, Button, Card, Chip, ErrorText, IconBubble, Overline, ProgressBar, Screen, Segmented } from "@/ui/kit";
import { colors, fonts, radius, space, type } from "@/ui/theme";

interface StudioLine {
  node_key: string;
  line: string;
  title: string;
}

interface ShadowResult {
  intelligibility: number;
  accent_proximity: number;
  intonation: number | null;
  critical: string[];
  heatmap: { phoneme: string; score: number; heard_as?: string | null }[];
  passed: boolean;
  final: boolean;
  attempts_left: number;
}

const MAX_ATTEMPTS = 3;
/** A sound scoring under this is shown as one to work on. */
const WEAK_SOUND = 70;

function Score({ label, value }: { label: string; value: number }) {
  return (
    <View style={{ gap: 4 }}>
      <View style={styles.scoreHead}>
        <Text style={type.callout}>{label}</Text>
        <Text style={type.headline}>{Math.round(value)}</Text>
      </View>
      <ProgressBar value={value / 100} tone={value >= 80 ? "success" : value >= 60 ? "warning" : "danger"} />
    </View>
  );
}

function Result({ result }: { result: ShadowResult }) {
  const { t } = useTranslation();
  const weak = result.heatmap.filter((p) => p.score < WEAK_SOUND);
  return (
    <View style={styles.result}>
      {result.passed && <Chip label={t("studio.passed")} tone="success" icon="checkmark-circle" />}
      <Score label={t("studio.intelligibility")} value={result.intelligibility} />
      <Score label={t("studio.accent")} value={result.accent_proximity} />
      {result.intonation !== null && <Score label={t("studio.intonation")} value={result.intonation} />}
      {weak.length > 0 && (
        <View style={{ gap: space(1) }}>
          <Overline>{t("studio.workOn")}</Overline>
          <View style={styles.sounds}>
            {weak.map((p, i) => (
              <View key={`${p.phoneme}-${i}`} style={styles.sound}>
                <Text style={styles.soundText}>{p.heard_as ? `/${p.phoneme}/ → /${p.heard_as}/` : `/${p.phoneme}/`}</Text>
              </View>
            ))}
          </View>
        </View>
      )}
      {!result.final && <Text style={type.caption}>{t("studio.attemptsLeft", { count: result.attempts_left })}</Text>}
    </View>
  );
}

export default function Studio() {
  const { t } = useTranslation();
  const api = useApi();
  const cities = useCities();
  const voice = useResource(() => api.get<{ status: string }>("/v1/voice"), [api]);
  const languages = cities.data?.map((c) => c.language) ?? [];
  const [chosen, setLanguage] = useState<CityEntry["language"] | null>(null);
  const language = chosen ?? languages[0] ?? null;
  const [lines, setLines] = useState<StudioLine[]>([]);
  const [results, setResults] = useState<Record<string, ShadowResult>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!language) return;
    api
      .get<StudioLine[]>(`/v1/studio/items?language=${language}`)
      .then((items) => {
        setLines(items);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [api, language]);

  return (
    <Screen back title={t("studio.title")}>
      <Body muted>{t("studio.intro")}</Body>
      {voice.data?.status === "active" ? (
        <Chip label={t("studio.inYourVoice")} tone="success" icon="person-circle" />
      ) : voice.data ? (
        <Card tone="accent" style={{ gap: space(1.5) }}>
          <View style={styles.row}>
            <IconBubble name="mic-circle" tone="accent" />
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={type.headline}>{t("studio.voiceTitle")}</Text>
              <Text style={type.caption}>{t("studio.voiceHint")}</Text>
            </View>
          </View>
          <Button label={t("studio.voiceAction")} kind="secondary" icon="arrow-forward" onPress={() => router.push("/voice")} />
        </Card>
      ) : null}
      {languages.length > 1 && language && (
        <Segmented options={languages.map((value) => ({ value, label: value.toUpperCase() }))} value={language} onChange={setLanguage} />
      )}
      <ErrorText message={cities.error ?? error} />
      {language &&
        lines.map((item) => {
          const result = results[item.line];
          const attempt = result ? MAX_ATTEMPTS - result.attempts_left + 1 : 1;
          return (
            <Card key={item.line} style={{ gap: space(1.5) }}>
              <Chip label={item.title} icon="musical-notes" />
              <Text style={styles.line}>{item.line}</Text>
              <View style={styles.actions}>
                <View style={{ flex: 1 }}>
                  <PlayButton api={api} path={`/v1/studio/reference?language=${language}&line=${encodeURIComponent(item.line)}`} />
                </View>
                {!result?.final && (
                  <View style={{ flex: 1 }}>
                    <Recorder<ShadowResult>
                      api={api}
                      language={language}
                      path="/v1/studio/shadow"
                      fields={{ line: item.line, attempt: String(attempt) }}
                      onDone={(r) => setResults((all) => ({ ...all, [item.line]: r }))}
                    />
                  </View>
                )}
              </View>
              {result && <Result result={result} />}
            </Card>
          );
        })}
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: space(1.5) },
  line: { fontFamily: fonts.displayBold, fontSize: 24, lineHeight: 31, color: colors.ink },
  actions: { flexDirection: "row", gap: space(1), alignItems: "flex-start" },
  result: { gap: space(1.25), paddingTop: space(1.5), borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  scoreHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" },
  sounds: { flexDirection: "row", flexWrap: "wrap", gap: space(0.75) },
  sound: { backgroundColor: colors.warningSoft, borderRadius: radius.pill, paddingHorizontal: space(1.25), paddingVertical: 4 },
  soundText: { fontFamily: fonts.semibold, fontSize: 14, color: colors.warning },
});
