/** One tense of a verb, a row per person: the subject quiet, the stem plain, the ending to learn picked out in colour,
 * and a dot on any form that breaks the pattern. Each row can be heard with its subject. */
import { useTranslation } from "react-i18next";
import { StyleSheet, Text, View } from "react-native";
import Animated, { FadeIn } from "react-native-reanimated";

import type { ApiClient } from "@/api/client";
import type { TenseTable } from "@/api/types";
import { SpeakButton } from "@/live/SpeakButton";
import { colors, fonts, radius, space, type } from "@/ui/theme";

export function VerbTable({ api, language, verb, table, compact = false }: { api: ApiClient; language: string; verb: string; table: TenseTable; compact?: boolean }) {
  const { t } = useTranslation();
  // The subject column fits the longest subject in this tense (« qu'ils/elles » in the subjunctive).
  const subjectWidth = Math.min(132, Math.max(48, Math.max(...table.forms.map((f) => f.subject.length)) * 8.6));
  return (
    <Animated.View key={table.tense} entering={FadeIn.duration(180)} style={styles.table}>
      {table.forms.map((form, person) => {
        const said = [form.subject, form.aux, form.stem + form.ending].filter(Boolean).join(" ").replace("' ", "'");
        return (
          <View key={person} style={[styles.row, person > 0 && styles.divider, compact && styles.rowCompact]} accessible accessibilityLabel={said}>
            <Text style={[styles.subject, { width: subjectWidth }]} numberOfLines={1}>
              {form.subject}
            </Text>
            <Text style={styles.form}>
              {form.aux ? <Text style={styles.aux}>{`${form.aux} `}</Text> : null}
              <Text>{form.stem}</Text>
              {form.ending ? <Text style={styles.ending}>{form.ending}</Text> : null}
            </Text>
            {form.irregular ? <View style={styles.dot} accessibilityLabel={t("verbs.ownForm")} /> : <View style={styles.dotSpace} />}
            <SpeakButton
              api={api}
              path={`/v1/conjugations/${language}/${verb}/say?tense=${table.tense}&person=${person}`}
              label={`${t("studio.listen")}: ${said}`}
              size={compact ? 16 : 18}
            />
          </View>
        );
      })}
    </Animated.View>
  );
}

/** What the colours in a verb table mean. */
export function VerbLegend({ table }: { table: TenseTable }) {
  const { t } = useTranslation();
  const ending = table.forms.find((f) => f.ending)?.ending;
  const irregular = table.forms.some((f) => f.irregular);
  if (!ending && !irregular) return null;
  return (
    <View style={styles.legend}>
      {ending && (
        <View style={styles.legendItem}>
          <Text style={[styles.ending, styles.legendSwatch]}>{`-${ending}`}</Text>
          <Text style={type.caption}>{t("verbs.endingLegend")}</Text>
        </View>
      )}
      {irregular && (
        <View style={styles.legendItem}>
          <View style={styles.dot} />
          <Text style={type.caption}>{t("verbs.ownForm")}</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  table: { backgroundColor: colors.card, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", gap: space(1), minHeight: 48, paddingLeft: space(1.75), paddingRight: space(1) },
  rowCompact: { minHeight: 42 },
  divider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  subject: { fontFamily: fonts.medium, fontSize: 15, color: colors.muted },
  form: { flex: 1, fontFamily: fonts.medium, fontSize: 18, color: colors.ink },
  aux: { color: colors.inkSoft, fontFamily: fonts.body },
  ending: { color: colors.sunset, fontFamily: fonts.bold },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.warning },
  dotSpace: { width: 8 },
  legend: { flexDirection: "row", flexWrap: "wrap", gap: space(2), alignItems: "center" },
  legendItem: { flexDirection: "row", alignItems: "center", gap: space(0.75) },
  legendSwatch: { fontSize: 14 },
});
