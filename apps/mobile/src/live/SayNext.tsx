/** Help in the middle of a conversation: the mission's steps stay in view, and a stuck learner can ask for three
 * things they could say next (with their meaning), which clear once they speak. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import Animated, { FadeInDown } from "react-native-reanimated";

import type { Suggestion } from "@/api/types";
import { useApi } from "@/state/auth";
import { Card, ErrorText } from "@/ui/kit";
import { colors, fonts, radius, space, type } from "@/ui/theme";

import type { Caption } from "./captions";

/** The mission's steps under the goal, folded to one line until opened. */
export function MissionSteps({ objectives }: { objectives: string[] }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(true);
  if (objectives.length === 0) return null;
  return (
    <View style={{ gap: space(0.5) }}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        accessibilityLabel={t("scene.steps")}
        onPress={() => setOpen(!open)}
        hitSlop={8}
        style={styles.stepsHead}
      >
        <Text style={[type.caption, { fontFamily: fonts.semibold, color: colors.accentDeep }]}>{t("scene.steps")}</Text>
        <Ionicons name={open ? "chevron-up" : "chevron-down"} size={14} color={colors.accentDeep} />
      </Pressable>
      {open &&
        objectives.map((o) => (
          <View key={o} style={styles.step}>
            <Ionicons name="ellipse-outline" size={12} color={colors.accent} style={{ marginTop: 3 }} />
            <Text style={[type.caption, { flex: 1, color: colors.ink }]}>{o}</Text>
          </View>
        ))}
    </View>
  );
}

export interface SayNext {
  ideas: Suggestion[] | null;
  busy: boolean;
  error: string | null;
  ask: () => void;
  clear: () => void;
}

/** Asks for ideas from the conversation so far; they clear when the learner next speaks. */
export function useSayNext(sceneId: string, captions: Caption[]): SayNext {
  const api = useApi();
  const [ideas, setIdeas] = useState<Suggestion[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const spoken = captions.filter((c) => c.speaker === "learner").length;
  const seen = useRef(spoken);
  useEffect(() => {
    if (spoken !== seen.current) {
      seen.current = spoken;
      setIdeas(null);
    }
  }, [spoken]);

  const ask = () => {
    setBusy(true);
    setError(null);
    const lines = captions.map((c) => ({ speaker: c.speaker, text: c.text }));
    api
      .post<Suggestion[]>(`/v1/scenes/${sceneId}/say-next`, { lines })
      .then(setIdeas)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  };
  return { ideas, busy, error, ask, clear: () => setIdeas(null) };
}

/** The ideas, under the conversation. */
export function SayNextCard({ help }: { help: SayNext }) {
  const { t } = useTranslation();
  if (help.busy && !help.ideas) {
    return (
      <View style={styles.thinking} accessibilityLiveRegion="polite">
        <ActivityIndicator color={colors.accent} />
        <Text style={type.callout}>{t("scene.sayNextBusy")}</Text>
      </View>
    );
  }
  if (!help.ideas) return <ErrorText message={help.error} onRetry={help.ask} />;
  return (
    <Animated.View entering={FadeInDown.duration(220)}>
      <Card tone="accent" style={{ gap: space(1.25) }}>
        <View style={styles.head}>
          <Ionicons name="bulb" size={16} color={colors.accentDeep} />
          <Text style={[type.overline, { flex: 1, color: colors.accentDeep }]}>{t("scene.sayNextTitle")}</Text>
          <Pressable accessibilityRole="button" accessibilityLabel={t("scene.sayNextHide")} onPress={help.clear} hitSlop={10}>
            <Ionicons name="close" size={18} color={colors.accentDeep} />
          </Pressable>
        </View>
        {help.ideas.length === 0 && <Text style={type.callout}>{t("scene.sayNextNone")}</Text>}
        {help.ideas.map((idea) => (
          <View key={idea.text} style={styles.idea} testID="say-next-idea">
            <Text style={[type.body, { fontFamily: fonts.semibold }]}>{idea.text}</Text>
            <Text style={[type.caption, { color: colors.inkSoft }]}>{idea.meaning}</Text>
          </View>
        ))}
        <Text style={type.caption}>{t("scene.sayNextTip")}</Text>
      </Card>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  stepsHead: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start" },
  step: { flexDirection: "row", gap: 6, alignItems: "flex-start" },
  head: { flexDirection: "row", alignItems: "center", gap: space(0.75) },
  idea: {
    backgroundColor: colors.card,
    borderRadius: radius.md,
    paddingHorizontal: space(1.5),
    paddingVertical: space(1),
    gap: 2,
  },
  thinking: { flexDirection: "row", alignItems: "center", gap: space(1), paddingHorizontal: space(0.5) },
});
