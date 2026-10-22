/** The language being worked on, as one small pill by the screen title: tap to switch to the other. It replaces a
 * full-width switcher on every screen, since the choice is made once and followed everywhere (decision 0029).
 * ``pack`` shows the exam in focus (the screen is about it); ``city`` names the other city, since the city in focus is
 * already the heading beside it. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { useTranslation } from "react-i18next";
import { Pressable, StyleSheet, Text } from "react-native";

import { useFocus } from "@/state/focus";
import { colors, fonts, radius, space } from "@/ui/theme";

export function FocusSwitch({ show = "pack" }: { show?: "pack" | "city" }) {
  const { t } = useTranslation();
  const focus = useFocus();
  const other = focus.cities.find((c) => c.language !== focus.language);
  if (!focus.city || !other) return null;
  const next = show === "city" ? other.name : other.pack_name;
  const label = show === "city" ? other.name : focus.city.pack_name;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={t("focus.switchTo", { name: next })}
      onPress={() => focus.choose(other.language)}
      style={({ pressed }) => [styles.pill, pressed && { opacity: 0.7 }]}
    >
      <Text style={styles.text} numberOfLines={1}>
        {label}
      </Text>
      <Ionicons name="swap-horizontal" size={14} color={colors.accent} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    minHeight: 30,
    maxWidth: 220,
    paddingHorizontal: space(1.25),
    borderRadius: radius.pill,
    backgroundColor: colors.accentSoft,
  },
  text: { fontFamily: fonts.semibold, fontSize: 13, color: colors.accentDeep, flexShrink: 1 },
});
