/** The scene as a mission: the brief before going in (what to do, what can be won, what it pays) and the debrief
 * after (what was achieved, how it ended, the coins earned). The rule a mission practises is taught beside it
 * (``MissionRule``); its other learning targets stay hidden. */
import Ionicons from "@expo/vector-icons/Ionicons";
import * as Haptics from "expo-haptics";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import Animated, { FadeInDown, ZoomIn } from "react-native-reanimated";

import type { Debrief, MissionBrief } from "@/api/types";
import { Card, Overline } from "@/ui/kit";
import { colors, fonts, radius, space, type } from "@/ui/theme";

function Coins({ amount, plus = true }: { amount: number; plus?: boolean }) {
  return (
    <View style={styles.coins}>
      <Ionicons name="cash" size={14} color={colors.sunset} />
      <Text style={styles.coinsText}>{`${plus ? "+" : ""}${amount}`}</Text>
    </View>
  );
}

export function MissionBriefCard({ goal, brief }: { goal: string; brief: MissionBrief | null }) {
  const { t } = useTranslation();
  return (
    <View style={styles.brief}>
      <View style={styles.head}>
        <Ionicons name="flag" size={16} color={colors.accentDeep} />
        <Text style={[type.overline, { flex: 1, color: colors.accentDeep }]}>{t(brief ? "mission.title" : "scene.goal")}</Text>
        {brief && <Coins amount={brief.reward} />}
      </View>
      <Text style={[type.body, { fontFamily: fonts.semibold }]}>{goal}</Text>
      {brief && brief.objectives.length > 0 && (
        <View style={{ gap: space(0.75) }}>
          {brief.objectives.map((o) => (
            <View key={o} style={styles.objective}>
              <Ionicons name="ellipse-outline" size={16} color={colors.accent} style={{ marginTop: 2 }} />
              <Text style={[type.callout, { flex: 1, color: colors.ink }]}>{o}</Text>
            </View>
          ))}
        </View>
      )}
      {brief?.win && (
        <View style={styles.win}>
          <Ionicons name="trophy" size={16} color={colors.sunset} style={{ marginTop: 2 }} />
          <Text style={[type.callout, { flex: 1 }]}>
            <Text style={{ fontFamily: fonts.semibold, color: colors.ink }}>{t("mission.win")} </Text>
            {brief.win}
          </Text>
        </View>
      )}
      {brief && <Text style={type.caption}>{t("mission.bonus", { count: brief.bonus })}</Text>}
    </View>
  );
}

const RESULT = {
  accomplished: {
    icon: "trophy",
    tone: colors.success,
    soft: colors.successSoft,
  },
  partial: {
    icon: "star-half",
    tone: colors.warning,
    soft: colors.warningSoft,
  },
  not_done: { icon: "refresh", tone: colors.inkSoft, soft: colors.paperDeep },
} as const;

export function MissionDebriefCard({ debrief, error }: { debrief: Debrief | null; error: string | null }) {
  const { t } = useTranslation();
  useEffect(() => {
    if (debrief?.result === "accomplished") void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  }, [debrief?.result]);

  if (!debrief) {
    return (
      <Card style={styles.judging}>
        {error ? <Text style={type.callout}>{t("mission.judgingFailed")}</Text> : <ActivityIndicator color={colors.accent} />}
        {!error && <Text style={[type.callout, { flex: 1 }]}>{t("mission.judging")}</Text>}
      </Card>
    );
  }
  const look = RESULT[debrief.result];
  return (
    <Animated.View entering={FadeInDown.duration(260)}>
      <Card style={{ gap: space(1.5) }}>
        <View style={[styles.banner, { backgroundColor: look.soft }]}>
          <Animated.View entering={ZoomIn.delay(120).springify()}>
            <Ionicons name={look.icon} size={30} color={look.tone} />
          </Animated.View>
          <View style={{ flex: 1, gap: 2 }}>
            <Overline>{t("mission.debrief")}</Overline>
            <Text style={[type.title, { color: look.tone }]}>{t(`mission.result.${debrief.result}`)}</Text>
          </View>
          {debrief.coins > 0 && (
            <Animated.View entering={ZoomIn.delay(320).springify()}>
              <Coins amount={debrief.coins} />
            </Animated.View>
          )}
        </View>
        <View style={{ gap: space(0.75) }}>
          {debrief.objectives.map((o, i) => (
            <Animated.View key={o.text} entering={FadeInDown.delay(200 + i * 120)} style={styles.objective}>
              <Ionicons
                name={o.met ? "checkmark-circle" : "ellipse-outline"}
                size={18}
                color={o.met ? colors.success : colors.muted}
                style={{ marginTop: 1 }}
              />
              <Text style={[type.callout, { flex: 1, color: o.met ? colors.ink : colors.muted }]}>{o.text}</Text>
            </Animated.View>
          ))}
        </View>
        {debrief.ending && (
          <View style={styles.win}>
            <Ionicons name="book" size={16} color={colors.accent} style={{ marginTop: 2 }} />
            <Text style={[type.callout, { flex: 1, fontStyle: "italic" }]}>{debrief.ending}</Text>
          </View>
        )}
        <Text style={type.caption}>{t(`mission.next.${debrief.result}`)}</Text>
      </Card>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  brief: {
    gap: space(1.25),
    backgroundColor: colors.accentSoft,
    borderRadius: radius.md,
    padding: space(1.75),
  },
  head: { flexDirection: "row", alignItems: "center", gap: space(0.75) },
  objective: { flexDirection: "row", alignItems: "flex-start", gap: space(1) },
  win: { flexDirection: "row", alignItems: "flex-start", gap: space(1) },
  coins: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: colors.card,
    borderRadius: radius.pill,
    paddingHorizontal: space(1),
    paddingVertical: 3,
  },
  coinsText: { fontFamily: fonts.semibold, fontSize: 14, color: colors.ink },
  banner: {
    flexDirection: "row",
    alignItems: "center",
    gap: space(1.5),
    borderRadius: radius.md,
    padding: space(1.5),
  },
  judging: { flexDirection: "row", alignItems: "center", gap: space(1.5) },
});
