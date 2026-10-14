import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { PlayButton } from "@/live/PlayButton";
import { Recorder } from "@/live/Recorder";
import { useApi } from "@/state/auth";
import { Body, Button, Card, ErrorText, Screen, Title } from "@/ui/kit";

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

export default function Studio() {
  const { t } = useTranslation();
  const api = useApi();
  const [language, setLanguage] = useState<"fr" | "en">("fr");
  const [lines, setLines] = useState<StudioLine[]>([]);
  const [results, setResults] = useState<Record<string, ShadowResult>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setResults({});
    api
      .get<StudioLine[]>(`/v1/studio/items?language=${language}`)
      .then((items) => {
        setLines(items);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [api, language]);

  return (
    <Screen>
      <Title>{t("studio.title")}</Title>
      <Button label={language.toUpperCase()} kind="secondary" onPress={() => setLanguage(language === "fr" ? "en" : "fr")} />
      <ErrorText message={error} />
      {lines.map((item) => {
        const result = results[item.line];
        const attempt = result ? MAX_ATTEMPTS - result.attempts_left + 1 : 1;
        return (
          <Card key={item.line}>
            <Title>{item.line}</Title>
            <Body muted>{item.title}</Body>
            <PlayButton
              api={api}
              path={`/v1/studio/reference?language=${language}&line=${encodeURIComponent(item.line)}`}
              label={`🔊 ${t("studio.listen")}`}
            />
            {result?.final ? null : (
              <Recorder<ShadowResult>
                api={api}
                language={language}
                path="/v1/studio/shadow"
                fields={{ line: item.line, attempt: String(attempt) }}
                onDone={(r) => setResults((all) => ({ ...all, [item.line]: r }))}
              />
            )}
            {result && (
              <>
                <Body>
                  {t("studio.intelligibility")}: {Math.round(result.intelligibility)} · {t("studio.accent")}: {Math.round(result.accent_proximity)}
                  {result.intonation === null ? "" : ` · ${t("studio.intonation")}: ${Math.round(result.intonation)}`}
                  {result.passed ? " ✓" : ""}
                </Body>
                <Body muted>
                  {result.heatmap
                    .filter((p) => p.score < 70)
                    .map((p) => (p.heard_as ? `/${p.phoneme}/ → /${p.heard_as}/` : `/${p.phoneme}/`))
                    .join("  ")}
                </Body>
                {!result.final && <Body muted>{t("studio.attemptsLeft", { count: result.attempts_left })}</Body>}
              </>
            )}
          </Card>
        );
      })}
    </Screen>
  );
}
