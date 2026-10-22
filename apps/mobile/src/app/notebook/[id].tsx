/** The night notebook (SPEC §15): what went well, what to fix with a lesson one tap away, and the cards added to
 * tomorrow's reviews. It is written after the day ends, so the screen waits for it with a friendly note. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import type { SessionView } from "@/api/types";
import { openKeyPoint } from "@/school/keyPoints";
import { useApi } from "@/state/auth";
import { UpNext } from "@/home/UpNext";
import { useResource } from "@/state/resource";
import { Button, Card, ErrorText, IconBubble, Overline, Screen } from "@/ui/kit";
import { colors, fonts, space, type } from "@/ui/theme";

const POLL_MS = 3000;

export default function NotebookScreen() {
  const { t } = useTranslation();
  const api = useApi();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [opening, setOpening] = useState<string | null>(null);
  const session = useResource(async () => {
    for (let i = 0; i < 40; i += 1) {
      const view = await api.get<SessionView>(`/v1/sessions/${id}`);
      if (view.notebook) return view;
      await new Promise((r) => setTimeout(r, POLL_MS));
    }
    return api.get<SessionView>(`/v1/sessions/${id}`);
  }, [id]);
  const notebook = session.data?.notebook;
  const footer = <UpNext after="story" />;

  if (!notebook) {
    return (
      <Screen back title={t("notebook.title")} eyebrow={t("notebook.eyebrow")} footer={footer}>
        <Card tone="accent" style={styles.waiting}>
          <IconBubble name="moon" tone="accent" size={56} />
          {session.loading ? (
            <>
              <ActivityIndicator color={colors.accent} />
              <Text style={[type.callout, { textAlign: "center" }]}>{t("notebook.writing")}</Text>
            </>
          ) : session.error ? (
            <ErrorText message={session.error} onRetry={session.reload} />
          ) : (
            <>
              <Text style={[type.callout, { textAlign: "center" }]}>{t("notebook.stillPreparing")}</Text>
              <Button label={t("notebook.retry")} kind="tinted" icon="refresh" onPress={session.reload} />
            </>
          )}
        </Card>
      </Screen>
    );
  }

  const practise = async (nodeKey: string) => {
    setOpening(nodeKey);
    try {
      await openKeyPoint(api, nodeKey);
    } catch {
      router.push("/school"); // not a grammar rule with key points: the School has the lessons
    } finally {
      setOpening(null);
    }
  };

  return (
    <Screen back title={t("notebook.title")} eyebrow={t("notebook.eyebrow")} footer={footer}>
      {notebook.encouragement ? (
        <Card tone="sunset" style={{ gap: space(1) }}>
          <View style={styles.row}>
            <Ionicons name="moon" size={18} color="#9A3E1E" />
            <Overline>{t("notebook.tonight")}</Overline>
          </View>
          <Text style={styles.encouragement}>{notebook.encouragement}</Text>
        </Card>
      ) : null}

      {notebook.strengths.length > 0 && (
        <Card style={{ gap: space(1.25) }}>
          <Overline>{t("notebook.wentWell")}</Overline>
          {notebook.strengths.map((s) => (
            <View key={s} style={styles.line}>
              <Ionicons name="star" size={18} color={colors.sunset} style={{ marginTop: 2 }} />
              <Text style={[type.body, { flex: 1 }]}>{s}</Text>
            </View>
          ))}
        </Card>
      )}

      <Card style={{ gap: space(1.5) }}>
        <Overline>{t("notebook.corrections")}</Overline>
        {notebook.corrections.length === 0 && <Text style={type.callout}>{t("notebook.nothingToFix")}</Text>}
        {notebook.corrections.map((c) => (
          <View key={`${c.node_key}-${c.learner_said}`} style={styles.correction}>
            <View style={styles.line}>
              <Ionicons name="close-circle" size={18} color={colors.danger} style={{ marginTop: 3 }} />
              <Text style={[type.body, styles.wrong]}>{c.learner_said}</Text>
            </View>
            <View style={styles.line}>
              <Ionicons name="checkmark-circle" size={18} color={colors.success} style={{ marginTop: 3 }} />
              <Text style={[type.body, { flex: 1, fontFamily: fonts.medium }]}>{c.correction}</Text>
            </View>
            {c.explanation ? <Text style={[type.caption, { marginLeft: 26 }]}>{c.explanation}</Text> : null}
            <View style={{ alignSelf: "flex-start", marginLeft: 18 }}>
              <Button compact kind="ghost" icon="school" label={t("notebook.practise")} busy={opening === c.node_key} onPress={() => void practise(c.node_key)} />
            </View>
          </View>
        ))}
      </Card>

      {notebook.review_items.length > 0 && (
        <Card tone="accent" style={{ gap: space(1.5) }}>
          <View style={styles.row}>
            <IconBubble name="albums" tone="accent" />
            <Text style={[type.headline, { flex: 1 }]}>{t("notebook.reviewCount", { count: notebook.review_items.length })}</Text>
          </View>
          <Button label={t("notebook.reviewNow")} icon="chatbubbles" onPress={() => router.replace("/phone")} />
        </Card>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  waiting: { alignItems: "center", paddingVertical: space(4), gap: space(1.5) },
  row: { flexDirection: "row", alignItems: "center", gap: space(1) },
  line: { flexDirection: "row", alignItems: "flex-start", gap: space(1) },
  encouragement: { fontFamily: fonts.display, fontSize: 19, lineHeight: 27, color: colors.ink },
  correction: { gap: space(0.75), paddingTop: space(1), borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  wrong: { flex: 1, color: colors.muted, textDecorationLine: "line-through" },
});
