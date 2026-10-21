/** The rule a mission practises, taught right in its brief (decision 0025): one slim row that never blocks "Start
 * talking", which opens in place into the rule a step at a time (verb tables, examples, the mistake to avoid), with the
 * full lesson a tap further. Every example can be heard in a native voice. Nothing here is required. */
import Ionicons from "@expo/vector-icons/Ionicons";
import * as Haptics from "expo-haptics";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, StyleSheet, Text, View } from "react-native";
import Animated, { FadeIn, LinearTransition } from "react-native-reanimated";

import type { KeyPoint, RuleCard as Card } from "@/api/types";
import { openKeyPoint } from "@/school/keyPoints";
import { RichText } from "@/school/RichText";
import { Teach } from "@/school/Teach";
import { VerbContext, openVerb, useVerbIndex } from "@/school/verbs";
import { languageOf } from "@/school/verbText";
import { SpeakButton } from "@/live/SpeakButton";
import { useApi } from "@/state/auth";
import { useResource } from "@/state/resource";
import { Button, ErrorText, Loading } from "@/ui/kit";
import { colors, fonts, radius, space, type } from "@/ui/theme";

export function MissionRule({ point }: { point: KeyPoint }) {
  const { t } = useTranslation();
  const api = useApi();
  const [open, setOpen] = useState(false);
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const language = languageOf(point.node_key);
  const card = useResource(
    () => (open ? api.get<Card>(`/v1/key-points/${encodeURIComponent(point.node_key)}/card`) : Promise.resolve(null)),
    [api, point.node_key, open],
  );
  const verbs = useVerbIndex(api, open ? language : null, point.node_key);
  const links = useMemo(() => ({ index: verbs?.index ?? null, open: (verb: string) => openVerb(language, verb, verbs?.focus[0]) }), [verbs, language]);

  const say = (part: "model" | "better" | "teach", index: number) => `/v1/key-points/${encodeURIComponent(point.node_key)}/say?part=${part}&index=${index}`;
  const toggle = () => {
    void Haptics.selectionAsync();
    setOpen((v) => !v);
  };
  const lesson = async () => {
    setOpening(true);
    setError(null);
    try {
      await openKeyPoint(api, point.node_key);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setOpening(false);
    }
  };

  return (
    <Animated.View layout={LinearTransition.duration(220)} style={[styles.card, open && styles.cardOpen]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${t("mission.ruleForThis")}: ${point.title}`}
        accessibilityState={{ expanded: open }}
        accessibilityHint={t(open ? "mission.ruleHide" : "mission.ruleShow")}
        onPress={toggle}
        style={({ pressed }) => [styles.head, pressed && { opacity: 0.75 }]}
      >
        <View style={styles.icon}>
          <Ionicons name={open ? "book" : "book-outline"} size={18} color={colors.accentDeep} />
        </View>
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={[type.overline, { color: colors.accentDeep }]}>{t("mission.ruleForThis")}</Text>
          <Text style={type.headline} numberOfLines={open ? undefined : 2}>
            {point.title}
          </Text>
        </View>
        <Ionicons name={open ? "chevron-up" : "chevron-down"} size={20} color={colors.accent} />
      </Pressable>

      {open && (
        <VerbContext.Provider value={links}>
          <Animated.View entering={FadeIn.duration(200)} style={styles.body}>
            {!card.data && !card.error && <Loading inline />}
            <ErrorText message={card.error} onRetry={card.reload} />
            {card.data && (
              <>
                <RichText text={card.data.rule} style={styles.rule} />
                {card.data.teach.length > 0 && <Teach api={api} language={language} steps={card.data.teach} sayPath={(n) => say("teach", n)} />}
                {card.data.models.length > 0 && (
                  <View style={{ gap: space(0.75) }}>
                    <Text style={type.overline}>{t("school.models")}</Text>
                    {card.data.models.slice(0, 3).map((m, i) => (
                      <View key={m} style={styles.line}>
                        <Ionicons name="chatbubble-ellipses" size={16} color={colors.accent} style={{ marginTop: 3 }} />
                        <RichText text={m} style={[type.body, { flex: 1 }]} />
                        <SpeakButton api={api} path={say("model", i)} label={`${t("studio.listen")}: ${m}`} size={18} />
                      </View>
                    ))}
                  </View>
                )}
                {card.data.watch_out[0] && (
                  <View style={styles.watch}>
                    <Text style={[type.overline, { color: colors.warning }]}>{t("school.watchOut")}</Text>
                    <View style={styles.line}>
                      <Ionicons name="close-circle" size={16} color={colors.danger} style={{ marginTop: 3 }} />
                      <Text style={[type.callout, styles.wrong]}>{card.data.watch_out[0].learner_said}</Text>
                    </View>
                    <View style={styles.line}>
                      <Ionicons name="checkmark-circle" size={16} color={colors.success} style={{ marginTop: 3 }} />
                      <RichText text={card.data.watch_out[0].better} style={[type.callout, { flex: 1, color: colors.ink }]} />
                      <SpeakButton api={api} path={say("better", 0)} label={`${t("studio.listen")}: ${card.data.watch_out[0].better}`} size={18} />
                    </View>
                  </View>
                )}
                <View style={styles.actions}>
                  <View style={{ flex: 1 }}>
                    <Button label={t("mission.fullLesson")} kind="tinted" icon="school" compact busy={opening} onPress={() => void lesson()} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Button label={t("mission.gotIt")} kind="secondary" icon="checkmark" compact onPress={toggle} />
                  </View>
                </View>
                <ErrorText message={error} />
              </>
            )}
          </Animated.View>
        </VerbContext.Provider>
      )}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.card, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.accentSoft, overflow: "hidden" },
  cardOpen: { borderColor: colors.accent },
  head: { flexDirection: "row", alignItems: "center", gap: space(1.5), padding: space(1.75), minHeight: 64 },
  icon: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.accentSoft, alignItems: "center", justifyContent: "center" },
  body: { gap: space(2), paddingHorizontal: space(1.75), paddingBottom: space(2) },
  rule: { fontFamily: fonts.display, fontSize: 18, lineHeight: 26, color: colors.ink },
  line: { flexDirection: "row", alignItems: "flex-start", gap: space(1) },
  watch: { gap: space(0.75), padding: space(1.5), borderRadius: radius.md, backgroundColor: colors.warningSoft },
  wrong: { flex: 1, color: colors.muted, textDecorationLine: "line-through" },
  actions: { flexDirection: "row", gap: space(1) },
});
