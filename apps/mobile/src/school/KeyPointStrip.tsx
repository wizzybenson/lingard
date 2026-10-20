/** Lessons offered inside the journey, never in its way: a slim card at a natural pause (before going into a place,
 * after a conversation, on a place on the map) with at most two lessons not learned yet. Tapping one opens it; the
 * learner can close the card, and a closed card stays away for that place for the rest of the day. */
import AsyncStorage from "@react-native-async-storage/async-storage";
import Ionicons from "@expo/vector-icons/Ionicons";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, StyleSheet, Text, View } from "react-native";
import Animated, { FadeInDown, FadeOut } from "react-native-reanimated";

import type { KeyPoint } from "@/api/types";
import { isoDate } from "@/ui/DatePicker";
import { KIND_ICONS, openKeyPoint } from "@/school/keyPoints";
import { useApi } from "@/state/auth";
import { ErrorText, IconBubble, ListRow } from "@/ui/kit";
import { colors, radius, space, type } from "@/ui/theme";

const MAX_OFFERED = 2;

/** The day's "closed" mark for one card, so it is not offered again until tomorrow. */
const closedKey = (id: string) => `lingard.offer.closed.${id}.${isoDate(new Date())}`;

export function KeyPointStrip({ id, eyebrow, points }: { id: string; eyebrow: string; points: KeyPoint[] | null | undefined }) {
  const { t } = useTranslation();
  const api = useApi();
  const [closed, setClosed] = useState<boolean | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const offered = (points ?? []).filter((k) => k.status !== "done").slice(0, MAX_OFFERED);

  useEffect(() => {
    let live = true;
    AsyncStorage.getItem(closedKey(id))
      .then((v) => live && setClosed(v === "1"))
      .catch(() => live && setClosed(false));
    return () => {
      live = false;
    };
  }, [id]);

  if (closed !== false || offered.length === 0) return null;

  const close = () => {
    setClosed(true);
    void AsyncStorage.setItem(closedKey(id), "1").catch(() => undefined);
  };
  const open = async (point: KeyPoint) => {
    setOpening(point.node_key);
    setError(null);
    try {
      await openKeyPoint(api, point.node_key);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setOpening(null);
    }
  };

  return (
    <Animated.View entering={FadeInDown.duration(240)} exiting={FadeOut.duration(160)} style={styles.card}>
      <View style={styles.head}>
        <Ionicons name="sparkles" size={14} color={colors.accentDeep} />
        <Text style={[type.overline, { flex: 1, color: colors.accentDeep }]}>{eyebrow}</Text>
        <Pressable accessibilityRole="button" accessibilityLabel={t("app.close")} hitSlop={12} onPress={close}>
          <Ionicons name="close" size={18} color={colors.muted} />
        </Pressable>
      </View>
      {offered.map((point) => (
        <ListRow
          key={point.node_key}
          title={point.title}
          subtitle={`${t(`school.kinds.${point.kind}`)} · ${t("units.minutes", { count: 5 })}`}
          leading={<IconBubble name={KIND_ICONS[point.kind][point.status === "open" ? 1 : 0]} tone="accent" size={36} />}
          disabled={opening !== null}
          onPress={() => void open(point)}
        />
      ))}
      <ErrorText message={error} />
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.card, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.accentSoft, overflow: "hidden" },
  head: { flexDirection: "row", alignItems: "center", gap: space(0.75), paddingHorizontal: space(2), paddingTop: space(1.5) },
});
