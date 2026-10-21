import { router } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { pinWeakness } from "@/auth/pin";
import { hasSavedPin, rememberedNames, savedPin } from "@/auth/remembered";
import { useAuth } from "@/state/auth";
import { LinearGradient } from "expo-linear-gradient";
import { StyleSheet, Text, TextInput, View } from "react-native";

import { chooseLocaleAtSignIn, currentLocale, UI_LOCALES, type UiLocale } from "@/i18n";
import { Button, Card, ErrorText, Field, Screen, Segmented, useKeyboardVisible } from "@/ui/kit";
import { fonts, gradients, radius, shadow, space } from "@/ui/theme";

export default function SignIn() {
  const { t } = useTranslation();
  const auth = useAuth();
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [invite, setInvite] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Before anything else: the interface in the learner's own language (the device's, unless they pick another).
  const [locale, setLocale] = useState<UiLocale>(currentLocale());
  const pinField = useRef<TextInput>(null);
  // Suggestions from this device: the last name pre-filled, others one tap away, and a saved PIN behind Face ID.
  const [names, setNames] = useState<string[]>([]);
  const [canUseSaved, setCanUseSaved] = useState(false);
  useEffect(() => {
    void rememberedNames().then((saved) => {
      setNames(saved);
      if (saved[0]) setName((typed) => typed || saved[0]!);
    });
  }, []);
  useEffect(() => {
    void hasSavedPin(name).then(setCanUseSaved);
  }, [name]);
  const fillSavedPin = async () => {
    const saved = await savedPin(name);
    if (saved) setPin(saved); // six digits: signs in by itself
  };
  // With the keyboard up, the brand folds away so the fields and the button stay in view on a small phone.
  const typing = useKeyboardVisible();

  const submit = async () => {
    setError(null);
    if (invite !== null) {
      const weak = pinWeakness(pin);
      if (weak) return setError(t(weak));
    }
    setBusy(true);
    try {
      if (invite !== null) await auth.redeem(invite, name, pin);
      else await auth.signIn(name, pin);
      router.replace("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  // Like a phone passcode: the sixth digit signs in. A number pad has no Return key, and on a small phone it covers the
  // button below the field. Each PIN is tried once, so a wrong one waits for the learner to change it.
  const tried = useRef<string | null>(null);
  useEffect(() => {
    if (invite !== null || !name.trim() || pin.length !== 6 || busy || tried.current === `${name}:${pin}`) return;
    tried.current = `${name}:${pin}`;
    void submit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pin, name, invite, busy]);

  return (
    <Screen>
      {!typing && (
        <LinearGradient colors={gradients.dusk} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={[styles.brand, shadow(3)]}>
          <View style={styles.mark}>
            <Text style={styles.markLetter}>L</Text>
          </View>
          <Text style={styles.title} accessibilityRole="header">
            {t("signIn.title")}
          </Text>
          <Text style={styles.tagline}>{t("signIn.tagline")}</Text>
        </LinearGradient>
      )}
      <Segmented
        options={UI_LOCALES.map(({ code, label }) => ({ value: code, label }))}
        value={locale}
        onChange={(code) => {
          chooseLocaleAtSignIn(code);
          setLocale(code);
        }}
      />
      <Card>
        {auth.status === "locked" && (
          <Button label={t("signIn.biometric")} kind="tinted" icon="scan" onPress={() => void auth.unlock().then((ok) => ok && router.replace("/"))} />
        )}
        <Field
          testID="sign-in-name"
          label={t("signIn.name")}
          value={name}
          onChangeText={setName}
          autoCapitalize="words"
          autoComplete="username"
          returnKeyType="next"
          submitBehavior="submit"
          onSubmitEditing={() => pinField.current?.focus()}
        />
        {names.filter((n) => n !== name).length > 0 && (
          <View style={styles.suggestions}>
            {names
              .filter((n) => n !== name)
              .map((n) => (
                <Button key={n} label={n} kind="secondary" compact icon="person-circle-outline" onPress={() => setName(n)} />
              ))}
          </View>
        )}
        <Field
          ref={pinField}
          testID="sign-in-pin"
          label={t("pin.label")}
          value={pin}
          onChangeText={(v) => setPin(v.replace(/\D/g, "").slice(0, 6))}
          keyboardType="number-pad"
          secureTextEntry
          autoComplete="off"
          textContentType="oneTimeCode"
        />
        {invite === null && canUseSaved && pin.length === 0 && (
          <Button label={t("signIn.useSavedPin")} kind="tinted" icon="key" onPress={() => void fillSavedPin()} />
        )}
        {invite !== null && <Field label={t("signIn.invite")} value={invite} onChangeText={setInvite} autoCapitalize="characters" />}
        <ErrorText message={error} />
        <Button
          label={invite !== null ? t("signIn.join") : t("signIn.submit")}
          icon="arrow-forward"
          busy={busy}
          disabled={!name || pin.length !== 6}
          onPress={() => void submit()}
        />
        {invite === null && <Button label={t("signIn.haveInvite")} kind="ghost" onPress={() => setInvite("")} />}
      </Card>
    </Screen>
  );
}

const styles = StyleSheet.create({
  suggestions: { flexDirection: "row", flexWrap: "wrap", gap: space(1) },
  brand: { borderRadius: radius.xl, padding: space(3), paddingTop: space(4), gap: space(1), marginTop: space(2) },
  mark: {
    width: 56,
    height: 56,
    borderRadius: 18,
    backgroundColor: "rgba(255,255,255,0.16)",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: space(1),
  },
  markLetter: { fontFamily: fonts.displayBold, fontSize: 32, color: "#fff", lineHeight: 38 },
  title: { fontFamily: fonts.displayBold, fontSize: 30, lineHeight: 36, color: "#fff" },
  tagline: { fontFamily: fonts.medium, fontSize: 16, lineHeight: 22, color: "rgba(255,255,255,0.85)" },
});
