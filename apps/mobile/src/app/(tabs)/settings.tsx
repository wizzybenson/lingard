import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { File, Paths } from "expo-file-system";
import { router } from "expo-router";
import * as Sharing from "expo-sharing";
import { Platform, Switch, View } from "react-native";

import type { Profile } from "@/api/types";
import { applyLocale, UI_LOCALES } from "@/i18n";
import { currentReminder, REMINDER_TIMES, reminderText, remindersSupported, setReminder, type ReminderTime } from "@/state/reminders";
import type { Today } from "@/api/types";
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
  const [notice, setNotice] = useState<string | null>(null);
  const [reminder, setReminderState] = useState<ReminderTime | null>(null);
  useEffect(() => {
    void currentReminder().then(setReminderState);
  }, []);

  const chooseReminder = async (time: ReminderTime | null) => {
    const today = await api.get<Today>("/v1/today").catch(() => ({ streak: 0, reviews_due: 0 }));
    const { title, body } = reminderText(t, today);
    if (await setReminder(time, title, body)) setReminderState(time);
    else setError(t("reminders.denied"));
  };

  /** The export is a zip behind auth: download it with the token, then save (web) or open the share sheet (phones). */
  const exportData = async () => {
    setError(null);
    try {
      if (Platform.OS === "web") {
        const url = URL.createObjectURL(await api.blob("/v1/me/export"));
        const link = document.createElement("a");
        link.href = url;
        link.download = "lingard-export.zip";
        link.click();
        URL.revokeObjectURL(url);
      } else {
        const source = await api.mediaSource("/v1/me/export");
        const target = new File(Paths.cache, "lingard-export.zip");
        if (target.exists) target.delete();
        const file = await File.downloadFileAsync(source.uri, target, { headers: source.headers });
        await Sharing.shareAsync(file.uri, { mimeType: "application/zip" });
      }
      setNotice(t("settings.exported"));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

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
      <Button label={t("settings.goal")} onPress={() => router.push("/goal")} />
      {remindersSupported && (
        <Card>
          <Body muted>{t("reminders.title")}</Body>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
            <Button label={t("reminders.off")} kind={reminder === null ? "primary" : "secondary"} onPress={() => void chooseReminder(null)} />
            {REMINDER_TIMES.map((time) => (
              <Button
                key={`${time.hour}:${time.minute}`}
                label={`${time.hour}:${String(time.minute).padStart(2, "0")}`}
                kind={reminder?.hour === time.hour && reminder.minute === time.minute ? "primary" : "secondary"}
                onPress={() => void chooseReminder(time)}
              />
            ))}
          </View>
        </Card>
      )}
      <Card>
        <Body muted>{t("settings.uiLanguage")}</Body>
        <View style={{ flexDirection: "row", gap: 8 }}>
          {UI_LOCALES.map(({ code, label }) => (
            <View key={code} style={{ flex: 1 }}>
              <Button
                label={label}
                kind={profile.data?.ui_locale === code ? "primary" : "secondary"}
                onPress={() => {
                  applyLocale(code);
                  void update({ ui_locale: code });
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
        <Button label={t("settings.export")} kind="secondary" onPress={() => void exportData()} />
        {notice && <Body muted>{notice}</Body>}
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
