import Ionicons from "@expo/vector-icons/Ionicons";
import * as Haptics from "expo-haptics";
import { Redirect, Tabs } from "expo-router";
import { useEffect, type ComponentProps } from "react";

import type { Profile } from "@/api/types";
import { applyLocale, currentLocale, takeSignInLocale } from "@/i18n";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/state/auth";
import { Loading, Screen } from "@/ui/kit";
import { colors, fonts, shadow } from "@/ui/theme";

type IconName = ComponentProps<typeof Ionicons>["name"];

const ICONS: Record<string, [IconName, IconName]> = {
  city: ["map-outline", "map"],
  phone: ["chatbubbles-outline", "chatbubbles"],
  school: ["school-outline", "school"],
  exam: ["document-text-outline", "document-text"],
  passport: ["ribbon-outline", "ribbon"],
  settings: ["settings-outline", "settings"],
};

export default function TabsLayout() {
  const { t } = useTranslation();
  const { status, pinChangeRequired, api } = useAuth();
  useEffect(() => {
    // The learner's chosen interface language follows them across devices. A first sign-in keeps the language they
    // used on the sign-in screen (the device language unless they picked another) and saves it.
    if (status !== "signedIn") return;
    const picked = takeSignInLocale();
    if (picked) {
      void api.patch("/v1/me", { ui_locale: picked }).catch(() => undefined);
      return;
    }
    void api
      .get<Profile>("/v1/me")
      .then((p) => (p.ui_locale ? applyLocale(p.ui_locale) : api.patch("/v1/me", { ui_locale: currentLocale() })))
      .catch(() => undefined);
  }, [status, api]);
  if (status === "booting") return <Screen><Loading inline /></Screen>; // the web is still trading its cookie for a token
  if (status !== "signedIn") return <Redirect href="/sign-in" />;
  if (pinChangeRequired) return <Redirect href="/change-pin" />;
  return (
    <Tabs
      screenListeners={{ tabPress: () => void Haptics.selectionAsync() }}
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.muted,
        tabBarLabelStyle: { fontFamily: fonts.medium, fontSize: 11 },
        tabBarStyle: { backgroundColor: colors.card, borderTopWidth: 0, ...shadow(2) },
        sceneStyle: { backgroundColor: colors.paper },
        tabBarIcon: ({ color, size, focused }) => (
          <Ionicons name={ICONS[route.name]?.[focused ? 1 : 0] ?? "ellipse-outline"} color={color} size={size - 1} />
        ),
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
