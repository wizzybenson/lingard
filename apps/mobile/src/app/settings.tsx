import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { File, Paths } from "expo-file-system";
import { router } from "expo-router";
import * as Sharing from "expo-sharing";
import { Platform, Switch, View } from "react-native";

import type { Profile, Today } from "@/api/types";
import { applyLocale, currentLocale, UI_LOCALES } from "@/i18n";
import { currentReminder, REMINDER_TIMES, reminderText, remindersSupported, setReminder, type ReminderTime } from "@/state/reminders";
import { useAuth } from "@/state/auth";
import { useFocus } from "@/state/focus";
import { useResource } from "@/state/resource";
import { Body, Button, Card, ErrorText, Field, ListRow, Loading, Screen, Section, Segmented } from "@/ui/kit";
import { colors, space } from "@/ui/theme";

export default function Settings() {
  const focus = useFocus();
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

  if (!profile.data) {
    return (
      <Screen back title={t("settings.title")}>
        <Loading />
      </Screen>
    );
  }
  const consents = profile.data.consents;
  const toggle = (key: keyof Profile["consents"]) => void update({ consents: { ...consents, [key]: !consents[key] } });

  const pad = { paddingHorizontal: space(2), paddingBottom: space(2) };
  const reminderKey = (time: ReminderTime | null) => (time ? `${time.hour}:${String(time.minute).padStart(2, "0")}` : "off");
  const consentSwitch = (key: keyof Profile["consents"], label: string) => (
    <Switch value={consents[key]} onValueChange={() => toggle(key)} accessibilityLabel={label} trackColor={{ true: colors.accent }} />
  );

  return (
    <Screen back title={t("settings.title")}>
      <ErrorText message={error} />
      <Section>
        <ListRow icon="flag" title={t("settings.goal")} onPress={() => router.push("/goal")} />
      </Section>

      <Section title={t("settings.preferences")}>
        {focus.cities.length > 1 && (
          <View>
            <ListRow icon="book" title={t("settings.learning")} />
            <View style={pad}>
              <Segmented
                options={focus.cities.map((c) => ({ value: c.language, label: t(`settings.learningName.${c.language}`) }))}
                value={focus.language}
                onChange={focus.choose}
              />
            </View>
          </View>
        )}
        <View>
          <ListRow icon="language" title={t("settings.uiLanguage")} />
          <View style={pad}>
            <Segmented
              options={UI_LOCALES.map(({ code, label }) => ({ value: code, label }))}
              value={profile.data.ui_locale ?? currentLocale()}
              onChange={(code) => {
                applyLocale(code);
                void update({ ui_locale: code });
              }}
            />
          </View>
        </View>
        <View>
          <ListRow icon="pulse" title={t("settings.intensity")} />
          <View style={pad}>
            <Segmented
              options={(["calm", "tense", "heated"] as const).map((level) => ({ value: level, label: t(`settings.${level}`) }))}
              value={profile.data.intensity_cap}
              onChange={(level) => void update({ intensity_cap: level })}
            />
          </View>
        </View>
        {remindersSupported && (
          <View>
            <ListRow icon="notifications" title={t("reminders.title")} />
            <View style={pad}>
              <Segmented
                options={[
                  { value: "off", label: t("reminders.off") },
                  ...REMINDER_TIMES.map((time) => ({ value: reminderKey(time), label: reminderKey(time) })),
                ]}
                value={reminderKey(reminder)}
                onChange={(key) => void chooseReminder(REMINDER_TIMES.find((time) => reminderKey(time) === key) ?? null)}
              />
            </View>
          </View>
        )}
      </Section>

      <Section title={t("settings.privacy")}>
        <ListRow
          icon="mic-circle"
          title={t("voice.title")}
          subtitle={t("settings.voiceCloneHint")}
          onPress={() => router.push("/voice")}
        />
        <ListRow
          icon="people"
          title={t("settings.leagueTitle")}
          subtitle={t("settings.leagueHint")}
          trailing={consentSwitch("friends_league", t("settings.league"))}
        />
        <ListRow
          icon="time"
          title={t("settings.keepAudioTitle")}
          subtitle={t("settings.keepAudioHint")}
          trailing={consentSwitch("audio_retention_extended", t("settings.keepAudio"))}
        />
        <ListRow
          icon="trash"
          title={t("settings.deleteClone")}
          onPress={() => void api.request("/v1/voice/clone", { method: "DELETE" }).catch((e: Error) => setError(e.message))}
        />
      </Section>

      <Section title={t("settings.account")} footer={notice ?? undefined}>
        <ListRow icon="download" title={t("settings.export")} onPress={() => void exportData()} />
        <ListRow icon="log-out" title={t("settings.signOut")} onPress={() => void signOut()} />
        <ListRow icon="warning" title={t("settings.deleteAccount")} onPress={() => setConfirmDelete(true)} />
      </Section>

      {confirmDelete && (
        <Card tone="danger">
          <Body>{t("settings.deleteConfirm")}</Body>
          <Field
            label={t("pin.current")}
            value={pin}
            onChangeText={(v) => setPin(v.replace(/\D/g, "").slice(0, 6))}
            keyboardType="number-pad"
            secureTextEntry
          />
          <Button
            label={t("settings.deleteAccount")}
            kind="danger"
            disabled={pin.length !== 6}
            onPress={() =>
              void api
                .post("/v1/me/delete", { pin })
                .then(() => signOut())
                .catch((e: Error) => setError(e.message))
            }
          />
          <Button
            label={t("app.cancel")}
            kind="ghost"
            onPress={() => {
              setConfirmDelete(false);
              setPin("");
            }}
          />
        </Card>
      )}
    </Screen>
  );
}
