/** A verb's tables as a sheet over the lesson or mission that opened it: a tab per tense (the rule's own first), each
 * form split into stem and ending, forms that break the pattern marked, every form playable with its subject. */
import Ionicons from "@expo/vector-icons/Ionicons";
import * as Haptics from "expo-haptics";
import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import type { VerbTables } from "@/api/types";
import { VerbLegend, VerbTable } from "@/school/VerbTable";
import { useApi } from "@/state/auth";
import { useResource } from "@/state/resource";
import { Chip, ErrorText, Loading } from "@/ui/kit";
import { colors, fonts, radius, space, type } from "@/ui/theme";

export default function VerbSheet() {
  const { t } = useTranslation();
  const api = useApi();
  const insets = useSafeAreaInsets();
  const { language, key, tense: focus } = useLocalSearchParams<{ language: string; key: string; tense?: string }>();
  const verb = useResource(() => api.get<VerbTables>(`/v1/conjugations/${language}/${encodeURIComponent(key)}`), [api, language, key]);
  const [picked, setPicked] = useState<string | null>(null);
  const tenses = verb.data?.tenses ?? [];
  const shown = tenses.find((x) => x.tense === (picked ?? focus)) ?? tenses[0];

  return (
    <ScrollView contentContainerStyle={[styles.page, { paddingBottom: insets.bottom + space(3) }]} keyboardShouldPersistTaps="handled">
      <View style={styles.head}>
        <View style={{ flex: 1, gap: space(0.75) }}>
          <Text style={type.overline}>{t("verbs.title")}</Text>
          <Text style={styles.infinitive} accessibilityRole="header">
            {verb.data?.infinitive ?? key}
          </Text>
        </View>
        {verb.data && (
          <Chip
            label={t(verb.data.irregular ? "verbs.irregular" : "verbs.regular")}
            tone={verb.data.irregular ? "warning" : "success"}
            icon={verb.data.irregular ? "shuffle" : "checkmark"}
          />
        )}
        <Pressable accessibilityRole="button" accessibilityLabel={t("app.close")} hitSlop={12} onPress={() => router.back()} style={styles.close}>
          <Ionicons name="close" size={20} color={colors.inkSoft} />
        </Pressable>
      </View>

      <ErrorText message={verb.error} onRetry={verb.reload} />
      {!verb.data && !verb.error && <Loading />}

      {shown && (
        <>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.tabs} accessibilityRole="tablist">
            {tenses.map((x) => {
              const on = x.tense === shown.tense;
              return (
                <Pressable
                  key={x.tense}
                  accessibilityRole="tab"
                  accessibilityState={{ selected: on }}
                  onPress={() => {
                    void Haptics.selectionAsync();
                    setPicked(x.tense);
                  }}
                  style={({ pressed }) => [styles.tab, on && styles.tabOn, pressed && !on && { opacity: 0.7 }]}
                >
                  <Text style={[styles.tabText, on && styles.tabTextOn]}>{x.label}</Text>
                  {x.tense === focus && <View style={[styles.focusDot, on && { backgroundColor: colors.accentInk }]} />}
                </Pressable>
              );
            })}
          </ScrollView>
          <View style={styles.meta}>
            <Text style={[type.headline, { flex: 1 }]}>{shown.label}</Text>
            <Text style={type.caption}>{t("verbs.level", { level: shown.band })}</Text>
          </View>
          <VerbTable api={api} language={language} verb={key} table={shown} />
          {shown.forms.some((f) => f.aux) && <Text style={type.caption}>{t("verbs.compound")}</Text>}
          <VerbLegend table={shown} />
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: space(2.5), paddingTop: space(3), gap: space(2) },
  head: { flexDirection: "row", alignItems: "flex-start", gap: space(1.5) },
  infinitive: { fontFamily: fonts.displayBold, fontSize: 32, lineHeight: 38, color: colors.ink, letterSpacing: -0.3 },
  close: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.paperDeep, alignItems: "center", justifyContent: "center" },
  tabs: { gap: space(1), paddingRight: space(2) },
  tab: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    minHeight: 38,
    paddingHorizontal: space(1.75),
    borderRadius: radius.pill,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
  },
  tabOn: { backgroundColor: colors.accent, borderColor: colors.accent },
  tabText: { fontFamily: fonts.semibold, fontSize: 14, color: colors.inkSoft },
  tabTextOn: { color: colors.accentInk },
  focusDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.sunset },
  meta: { flexDirection: "row", alignItems: "baseline", gap: space(1) },
});
