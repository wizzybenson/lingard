import { getLocales } from "expo-localization";
import i18n from "i18next";
import { I18nManager, Platform } from "react-native";
import { initReactI18next } from "react-i18next";

import ar from "./ar.json";
import en from "./en.json";
import fr from "./fr.json";

export const resources = { en: { translation: en }, fr: { translation: fr }, ar: { translation: ar } } as const;
export type UiLocale = keyof typeof resources;
export const UI_LOCALES: { code: UiLocale; label: string }[] = [
  { code: "en", label: "English" },
  { code: "fr", label: "Français" },
  { code: "ar", label: "العربية" },
];
const RTL: ReadonlySet<UiLocale> = new Set(["ar"]);

let chosenAtSignIn: UiLocale | null = null;

/** The learner picked a language on the sign-in screen: it wins over the one saved in their profile. */
export function chooseLocaleAtSignIn(locale: UiLocale): void {
  chosenAtSignIn = locale;
  applyLocale(locale);
}

/** The sign-in screen's choice, once (null when the learner didn't pick one there). */
export function takeSignInLocale(): UiLocale | null {
  const chosen = chosenAtSignIn;
  chosenAtSignIn = null;
  return chosen;
}

/** The interface language on screen now. */
export function currentLocale(): UiLocale {
  return (i18n.language in resources ? i18n.language : "en") as UiLocale;
}

export function deviceLocale(): UiLocale {
  const code = getLocales()[0]?.languageCode ?? "en";
  return code in resources ? (code as UiLocale) : "en";
}

/** Switch the interface language and text direction. On the web the page flips at once; on phones React Native
 * applies a direction change on the next app start. */
export function applyLocale(locale: UiLocale): void {
  void i18n.changeLanguage(locale);
  const rtl = RTL.has(locale);
  if (Platform.OS === "web") {
    if (typeof document !== "undefined") {
      document.documentElement.dir = rtl ? "rtl" : "ltr";
      document.documentElement.lang = locale;
    }
  } else if (I18nManager.isRTL !== rtl) {
    I18nManager.allowRTL(rtl);
    I18nManager.forceRTL(rtl);
  }
}

void i18n.use(initReactI18next).init({
  resources,
  lng: deviceLocale(),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});
applyLocale(deviceLocale());

export default i18n;
