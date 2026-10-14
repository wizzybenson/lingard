import { router } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { pinWeakness } from "@/auth/pin";
import { useAuth } from "@/state/auth";
import { Body, Button, ErrorText, Field, Screen, Title } from "@/ui/kit";

export default function SignIn() {
  const { t } = useTranslation();
  const auth = useAuth();
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [invite, setInvite] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <Screen>
      <Title>{t("signIn.title")}</Title>
      {auth.status === "locked" && (
        <Button label={t("signIn.biometric")} kind="secondary" onPress={() => void auth.unlock().then((ok) => ok && router.replace("/"))} />
      )}
      <Field label={t("signIn.name")} value={name} onChangeText={setName} autoCapitalize="words" autoComplete="username" />
      <Field
        label={t("pin.label")}
        value={pin}
        onChangeText={(v) => setPin(v.replace(/\D/g, "").slice(0, 6))}
        keyboardType="number-pad"
        secureTextEntry
        autoComplete="off"
        textContentType="oneTimeCode"
      />
      {invite !== null && <Field label={t("signIn.invite")} value={invite} onChangeText={setInvite} autoCapitalize="characters" />}
      <ErrorText message={error} />
      <Button label={invite !== null ? t("signIn.join") : t("signIn.submit")} busy={busy} disabled={!name || pin.length !== 6} onPress={() => void submit()} />
      {invite === null && <Button label={t("signIn.haveInvite")} kind="secondary" onPress={() => setInvite("")} />}
      <Body muted>Lingard</Body>
    </Screen>
  );
}
