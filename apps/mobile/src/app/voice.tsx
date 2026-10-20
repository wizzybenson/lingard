/** Your voice: with consent, read a short passage once; Lingard makes a voice clone so Accent Studio can play each
 * line in your own voice with a native accent (the golden self). Deletable here at any time. */
import { router } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Switch, Text, View } from "react-native";

import type { CityEntry, Profile } from "@/api/types";
import { Recorder } from "@/live/Recorder";
import { useApi } from "@/state/auth";
import { useCities } from "@/state/cities";
import { useResource } from "@/state/resource";
import { Body, Button, Card, ErrorText, IconBubble, ListRow, Loading, Overline, Screen, Section, Segmented, Title } from "@/ui/kit";
import { colors, space, type } from "@/ui/theme";

interface VoiceView {
  status: "none" | "active" | "deleted";
  provider: string | null;
  consent_at: string | null;
}

interface Passage {
  text: string;
  min_seconds: number;
  max_seconds: number;
}

export default function Voice() {
  const { t } = useTranslation();
  const api = useApi();
  const cities = useCities();
  const voice = useResource(() => api.get<VoiceView>("/v1/voice"), [api]);
  const profile = useResource(() => api.get<Profile>("/v1/me"), [api]);
  const languages = cities.data?.map((c) => c.language) ?? [];
  const [chosen, setChosen] = useState<CityEntry["language"] | null>(null);
  const language = chosen ?? languages[0] ?? null;
  const passage = useResource(() => (language ? api.get<Passage>(`/v1/voice/passage?language=${language}`) : Promise.resolve(null)), [api, language]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!voice.data || !profile.data) {
    return <Screen back title={t("voice.title")}>{voice.error || profile.error ? <ErrorText message={voice.error ?? profile.error} onRetry={voice.reload} /> : <Loading />}</Screen>;
  }
  const consents = profile.data.consents;

  const setConsent = async (value: boolean) => {
    setError(null);
    try {
      await api.request("/v1/me", { method: "PATCH", body: JSON.stringify({ consents: { ...consents, voice_clone: value } }) });
      profile.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const remove = async () => {
    setError(null);
    setBusy(true);
    try {
      await api.request("/v1/voice/clone", { method: "DELETE" });
      voice.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (voice.data.status === "active") {
    return (
      <Screen back title={t("voice.title")}>
        <Card tone="success" style={{ gap: space(1.5) }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: space(1.5) }}>
            <IconBubble name="checkmark-circle" tone="success" size={48} />
            <View style={{ flex: 1, gap: 2 }}>
              <Title>{t("voice.ready")}</Title>
              <Text style={type.caption}>{t("voice.readyHint")}</Text>
            </View>
          </View>
          <Button label={t("voice.tryStudio")} icon="mic" onPress={() => router.push("/studio")} />
        </Card>
        <Section footer={t("voice.deleteHint")}>
          <ListRow icon="trash" title={t("voice.delete")} disabled={busy} onPress={() => void remove()} />
        </Section>
        <ErrorText message={error} />
      </Screen>
    );
  }

  return (
    <Screen back title={t("voice.title")}>
      <Body muted>{t("voice.intro")}</Body>
      <Section>
        <ListRow
          icon="shield-checkmark"
          title={t("voice.consentTitle")}
          subtitle={t("settings.voiceCloneConsent")}
          trailing={
            <Switch
              value={consents.voice_clone}
              onValueChange={(value) => void setConsent(value)}
              accessibilityLabel={t("settings.voiceCloneConsent")}
              trackColor={{ true: colors.accent }}
            />
          }
        />
      </Section>
      {languages.length > 1 && language && (
        <Segmented options={languages.map((value) => ({ value, label: value.toUpperCase() }))} value={language} onChange={setChosen} />
      )}
      <Card style={{ gap: space(1.5) }}>
        <Overline>{t("voice.passageTitle")}</Overline>
        {passage.data ? <Text style={[type.body, { fontSize: 18, lineHeight: 28 }]}>{passage.data.text}</Text> : <Loading />}
        <Text style={type.caption}>{t("voice.readHint", { min: passage.data?.min_seconds ?? 20 })}</Text>
        {language && (
          <Recorder<VoiceView>
            api={api}
            language={language}
            path="/v1/voice/clone"
            fileField="sample"
            fields={{ consent: "true" }}
            disabled={!consents.voice_clone}
            onDone={() => voice.reload()}
          />
        )}
        {!consents.voice_clone && <Text style={type.caption}>{t("voice.consentNeeded")}</Text>}
      </Card>
      <ErrorText message={error ?? passage.error} />
    </Screen>
  );
}
