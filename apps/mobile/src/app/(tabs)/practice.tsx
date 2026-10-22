/** Practice: the three ways to train outside the story, one line each saying what is next in it (decision 0029).
 * Review brings back what is about to be forgotten, Sounds is the Accent Studio, Lessons is the School. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { router, useFocusEffect, type Href } from "expo-router";
import { useTranslation } from "react-i18next";
import { I18nManager, Pressable, StyleSheet, Text, View } from "react-native";
import Animated, { FadeInDown } from "react-native-reanimated";

import type { Today } from "@/api/types";
import { stopTitle } from "@/home/stops";
import { useApi } from "@/state/auth";
import { useResource } from "@/state/resource";
import { FocusSwitch } from "@/ui/FocusSwitch";
import { ErrorText, IconBubble, Screen, type IconName } from "@/ui/kit";
import { colors, radius, shadow, space, type } from "@/ui/theme";

function Tile({ icon, tone, title, next, href, index }: { icon: IconName; tone: "accent" | "sunset" | "success"; title: string; next: string; href: Href; index: number }) {
  return (
    <Animated.View entering={FadeInDown.delay(index * 70).duration(320)}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={title}
        accessibilityHint={next}
        onPress={() => router.push(href)}
        style={({ pressed }) => [styles.tile, shadow(1), pressed && { opacity: 0.85, transform: [{ scale: 0.99 }] }]}
      >
        <IconBubble name={icon} tone={tone} size={48} />
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={type.title}>{title}</Text>
          <Text style={type.callout} numberOfLines={2}>
            {next}
          </Text>
        </View>
        <Ionicons name={I18nManager.isRTL ? "chevron-back" : "chevron-forward"} size={18} color={colors.muted} />
      </Pressable>
    </Animated.View>
  );
}

export default function Practice() {
  const { t } = useTranslation();
  const api = useApi();
  const today = useResource(() => api.get<Today>("/v1/today"), [api]);
  useFocusEffect(today.reload);
  const sounds = today.data?.path.find((s) => s.kind === "sounds");
  const reviews = today.data?.reviews_due ?? 0;
  // The lesson the coach picked for today: a mistake to mend first, else the new rule.
  const lesson = today.data?.path.find((s) => s.kind === "fix" && !s.done) ?? today.data?.path.find((s) => s.kind === "learn" && s.title);
  const rule = today.data?.next_key_point;
  return (
    <Screen title={t("practice.title")} accessory={<FocusSwitch />} onRefresh={today.reload}>
      <ErrorText message={today.error} onRetry={today.reload} />
      <Tile
        icon="flash"
        tone="accent"
        title={t("tabs.phone")}
        next={reviews > 0 ? t("practice.reviewsWaiting", { count: reviews }) : t("practice.caughtUp")}
        href="/phone"
        index={0}
      />
      <Tile
        icon="mic"
        tone="sunset"
        title={t("practice.sounds")}
        next={sounds?.example ? t("practice.soundNext", { example: sounds.example }) : t("practice.soundsHint")}
        href="/studio"
        index={1}
      />
      <Tile
        icon="book"
        tone="success"
        title={t("practice.lessons")}
        next={lesson ? stopTitle(t, lesson) : rule ? t("practice.lessonNext", { title: rule.title }) : t("practice.lessonsHint")}
        href="/school"
        index={2}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  tile: {
    flexDirection: "row",
    alignItems: "center",
    gap: space(1.75),
    padding: space(2.25),
    borderRadius: radius.lg,
    backgroundColor: colors.card,
  },
});
