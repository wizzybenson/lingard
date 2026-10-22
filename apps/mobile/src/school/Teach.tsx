/** A rule taught a step at a time before anything is asked of the learner: each step one idea, made concrete by a
 * verb's table (endings in colour), a pattern table or examples to hear. Verbs anywhere in it open their full tables. */
import Ionicons from "@expo/vector-icons/Ionicons";
import * as Haptics from "expo-haptics";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, StyleSheet, Text, View } from "react-native";
import Animated, { FadeInDown } from "react-native-reanimated";

import type { ApiClient } from "@/api/client";
import type { TeachStep, TeachTable } from "@/contracts/generated";
import { SpeakButton } from "@/live/SpeakButton";
import { RichText } from "@/school/RichText";
import { VerbTable } from "@/school/VerbTable";
import { openVerb, useVerbTables } from "@/school/verbs";
import { colors, fonts, radius, space, type } from "@/ui/theme";

function StepTable({ table }: { table: TeachTable }) {
  const head = table.head ?? [];
  return (
    <View style={styles.grid} accessibilityRole="summary">
      {head.length > 0 && (
        <View style={[styles.gridRow, styles.gridHead]}>
          {head.map((cell, i) => (
            <Text key={i} style={[styles.gridCell, styles.gridHeadText, i === 0 && styles.gridFirst]}>
              {cell}
            </Text>
          ))}
        </View>
      )}
      {table.rows.map((row, r) => (
        <View key={r} style={[styles.gridRow, r > 0 && styles.gridDivider]}>
          {row.map((cell, i) => (
            <RichText key={i} text={cell} style={[styles.gridCell, i === 0 && styles.gridFirst]} />
          ))}
        </View>
      ))}
    </View>
  );
}

function StepVerb({ api, language, verb, tense }: { api: ApiClient; language: string; verb: string; tense?: string | null }) {
  const { t } = useTranslation();
  const tables = useVerbTables(api, language, verb);
  const table = tables?.tenses.find((x) => x.tense === tense) ?? tables?.tenses[0];
  if (!tables || !table) return <View style={styles.tablePlaceholder} />;
  return (
    <View style={{ gap: space(1) }}>
      <View style={styles.verbHead}>
        <Text style={styles.verbName}>{tables.infinitive}</Text>
        <Text style={[type.caption, { flex: 1 }]}>{table.label}</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("verbs.allTenses")}
          accessibilityHint={tables.infinitive}
          onPress={() => openVerb(language, verb, table.tense)}
          hitSlop={8}
          style={({ pressed }) => [styles.allTenses, pressed && { opacity: 0.7 }]}
        >
          <Text style={styles.allTensesText}>{t("verbs.allTenses")}</Text>
          <Ionicons name="chevron-forward" size={14} color={colors.accent} />
        </Pressable>
      </View>
      <VerbTable api={api} language={language} verb={verb} table={table} compact />
    </View>
  );
}

/** ``sayPath(n)``: where the n-th example of the whole teaching is heard (a lesson's own lines); none in a rule card.
 * ``paced``: one step at a time, the next on "Got it", so a rule arrives as a few small ideas rather than a page
 * (decision 0029); ``onAllShown`` fires once the last step is out. */
export function Teach({
  api,
  language,
  steps,
  sayPath,
  paced = false,
  onAllShown,
}: {
  api: ApiClient;
  language: string;
  steps: TeachStep[];
  sayPath?: (n: number) => string;
  paced?: boolean;
  onAllShown?: () => void;
}) {
  const { t } = useTranslation();
  const [revealed, setRevealed] = useState(1);
  // Unpaced (or no longer: the learner moved on to practice) shows every step.
  const shown = paced ? revealed : steps.length;
  const more = shown < steps.length;
  const next = () => {
    void Haptics.selectionAsync();
    setRevealed(shown + 1);
    if (shown + 1 >= steps.length) onAllShown?.();
  };
  let example = 0;
  return (
    <View style={{ gap: space(2) }}>
      {steps.slice(0, shown).map((step, i) => (
        <Animated.View key={i} entering={FadeInDown.delay(Math.min(i, 4) * 70).duration(240)} style={styles.step}>
          <View style={styles.stepHead}>
            <View style={styles.number}>
              <Text style={styles.numberText}>{i + 1}</Text>
            </View>
            <RichText text={step.say} links="highlighted" style={[type.body, { flex: 1, fontFamily: fonts.medium }]} />
          </View>
          {step.verb ? <StepVerb api={api} language={language} verb={step.verb} tense={step.tense} /> : null}
          {step.table ? <StepTable table={step.table} /> : null}
          {(step.examples ?? []).map((line) => {
            const n = example++;
            return (
              <View key={`${i}-${n}`} style={styles.example}>
                <Ionicons name="chatbubble-ellipses-outline" size={16} color={colors.accent} style={{ marginTop: 4 }} />
                <RichText text={line} style={[type.body, { flex: 1 }]} />
                {sayPath ? <SpeakButton api={api} path={sayPath(n)} label={`${t("studio.listen")}: ${line.replaceAll("**", "")}`} size={18} /> : null}
              </View>
            );
          })}
        </Animated.View>
      ))}
      {more && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("school.gotItNext", { n: shown + 1, total: steps.length })}
          onPress={next}
          style={({ pressed }) => [styles.next, pressed && { opacity: 0.8 }]}
        >
          <Text style={styles.nextText}>{t("school.gotItNext", { n: shown + 1, total: steps.length })}</Text>
          <Ionicons name="arrow-down" size={16} color={colors.accentDeep} />
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  step: { gap: space(1.5) },
  next: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: space(0.75),
    minHeight: 46,
    borderRadius: radius.md,
    backgroundColor: colors.accentSoft,
  },
  nextText: { fontFamily: fonts.semibold, fontSize: 15, color: colors.accentDeep },
  stepHead: { flexDirection: "row", alignItems: "flex-start", gap: space(1.25) },
  number: { width: 26, height: 26, borderRadius: 13, backgroundColor: colors.accent, alignItems: "center", justifyContent: "center", marginTop: 1 },
  numberText: { fontFamily: fonts.bold, fontSize: 13, color: colors.accentInk },
  example: { flexDirection: "row", alignItems: "flex-start", gap: space(1), paddingLeft: space(0.5) },
  verbHead: { flexDirection: "row", alignItems: "baseline", gap: space(1) },
  verbName: { fontFamily: fonts.display, fontSize: 19, color: colors.ink },
  allTenses: { flexDirection: "row", alignItems: "center", gap: 2, minHeight: 32 },
  allTensesText: { fontFamily: fonts.semibold, fontSize: 13, color: colors.accent },
  tablePlaceholder: { height: 6 * 42, borderRadius: radius.md, backgroundColor: colors.paperDeep },
  grid: { borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, overflow: "hidden" },
  gridRow: { flexDirection: "row", alignItems: "center", minHeight: 42, paddingHorizontal: space(1.5), gap: space(1) },
  gridHead: { backgroundColor: colors.paper, minHeight: 34 },
  gridHeadText: { fontFamily: fonts.semibold, fontSize: 12, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.6 },
  gridDivider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  gridCell: { flex: 1, fontFamily: fonts.medium, fontSize: 15, color: colors.ink, paddingVertical: space(0.75) },
  gridFirst: { flex: 0.8, color: colors.inkSoft },
});
