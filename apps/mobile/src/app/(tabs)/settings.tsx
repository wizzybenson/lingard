import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Switch, View } from "react-native";

import type { Profile } from "@/api/types";
import i18n from "@/i18n";
import { useAuth } from "@/state/auth";
import { useResource } from "@/state/resource";
import { Body, Button, Card, ErrorText, Field, Loading, Screen, Title } from "@/ui/kit";

export default function Settings() {
  const { t } = useTranslation();
  const { api, signOut } = useAuth();
  const profile = useResource(() => api.get<Profile>("/v1/me"));
  const [error, setError] = useState<string | null>(null);
  const [pin, setPin] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const update = async (patch: Partial<Profile>) => {
    try {
      await api.patch("/v1/me", patch);
      profile.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (!profile.data) return <Screen><Loading /></Screen>;
  const consents = profile.data.consents;
  const toggle = (key: keyof Profile["consents"]) => void update({ consents: { ...consents, [key]: !consents[key] } });

  return (
    <Screen>
      <Title>{t("settings.title")}</Title>
      <ErrorText message={error} />
      <Card>
        <Body muted>{t("settings.uiLanguage")}</Body>
        <View style={{ flexDirection: "row", gap: 8 }}>
          {(["en", "fr"] as const).map((locale) => (
            <View key={locale} style={{ flex: 1 }}>
              <Button
                label={locale.toUpperCase()}
                kind={profile.data?.ui_locale === locale ? "primary" : "secondary"}
                onPress={() => {
                  void i18n.changeLanguage(locale);
                  void update({ ui_locale: locale });
                }}
              />
            </View>
          ))}
        </View>
      </Card>
      <Card>
        <Body muted>{t("settings.intensity")}</Body>
        {(["calm", "tense", "heated"] as const).map((level) => (
          <Button key={level} label={t(`settings.${level}`)} kind={profile.data?.intensity_cap === level ? "primary" : "secondary"} onPress={() => void update({ intensity_cap: level })} />
        ))}
      </Card>
      <Card>
        {(
          [
            ["voice_clone", "settings.voiceCloneConsent"],
            ["friends_league", "settings.league"],
            ["audio_retention_extended", "settings.keepAudio"],
          ] as const
        ).map(([key, label]) => (
          <View key={key} style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Switch value={consents[key]} onValueChange={() => toggle(key)} accessibilityLabel={t(label)} />
            <View style={{ flex: 1 }}>
              <Body>{t(label)}</Body>
            </View>
          </View>
        ))}
        <Button label={t("settings.deleteClone")} kind="secondary" onPress={() => void api.request("/v1/voice/clone", { method: "DELETE" }).catch((e: Error) => setError(e.message))} />
      </Card>
      <Card>
        <Button label={t("settings.export")} kind="secondary" onPress={() => void api.mediaSource("/v1/me/export").then((s) => setError(`Export: ${s.uri}`))} />
        {!confirmDelete ? (
          <Button label={t("settings.deleteAccount")} kind="danger" onPress={() => setConfirmDelete(true)} />
        ) : (
          <>
            <Field label={t("pin.current")} value={pin} onChangeText={(v) => setPin(v.replace(/\D/g, "").slice(0, 6))} keyboardType="number-pad" secureTextEntry />
            <Button
              label={t("settings.deleteAccount")}
              kind="danger"
              disabled={pin.length !== 6}
              onPress={() => void api.post("/v1/me/delete", { pin }).then(() => signOut()).catch((e: Error) => setError(e.message))}
            />
          </>
        )}
        <Button label={t("settings.signOut")} kind="secondary" onPress={() => void signOut()} />
      </Card>
    </Screen>
  );
}
