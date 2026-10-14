import { getLocales } from "expo-localization";
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./en.json";
import fr from "./fr.json";

export const resources = { en: { translation: en }, fr: { translation: fr } } as const;
export type UiLocale = keyof typeof resources;

export function deviceLocale(): UiLocale {
  const code = getLocales()[0]?.languageCode ?? "en";
  return code === "fr" ? "fr" : "en";
}

void i18n.use(initReactI18next).init({
  resources,
  lng: deviceLocale(),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

export default i18n;
