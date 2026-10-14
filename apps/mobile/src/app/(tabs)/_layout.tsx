import Ionicons from "@expo/vector-icons/Ionicons";
import { Redirect, Tabs } from "expo-router";
import type { ComponentProps } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/state/auth";
import { colors } from "@/ui/theme";

type IconName = ComponentProps<typeof Ionicons>["name"];

const ICONS: Record<string, IconName> = {
  city: "map-outline",
  phone: "phone-portrait-outline",
  school: "school-outline",
  exam: "document-text-outline",
  passport: "ribbon-outline",
  settings: "settings-outline",
};

export default function TabsLayout() {
  const { t } = useTranslation();
  const { status, pinChangeRequired } = useAuth();
  if (status !== "signedIn") return <Redirect href="/sign-in" />;
  if (pinChangeRequired) return <Redirect href="/change-pin" />;
  return (
    <Tabs
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: colors.accent,
        tabBarIcon: ({ color, size }) => <Ionicons name={ICONS[route.name] ?? "ellipse-outline"} color={color} size={size} />,
      })}
    >
      <Tabs.Screen name="city" options={{ title: t("tabs.city") }} />
      <Tabs.Screen name="phone" options={{ title: t("tabs.phone") }} />
      <Tabs.Screen name="school" options={{ title: t("tabs.school") }} />
      <Tabs.Screen name="exam" options={{ title: t("tabs.exam") }} />
      <Tabs.Screen name="passport" options={{ title: t("tabs.passport") }} />
      <Tabs.Screen name="settings" options={{ title: t("tabs.settings") }} />
    </Tabs>
  );
}
