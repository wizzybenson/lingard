import { router } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { pinWeakness } from "@/auth/pin";
import { useAuth } from "@/state/auth";
import { Body, Button, ErrorText, Field, Screen, Title } from "@/ui/kit";

export default function ChangePin() {
  const { t } = useTranslation();
  const { api, pinChanged, signInPin, signOut } = useAuth();
  const [typed, setTyped] = useState("");
  const current = signInPin ?? typed; // right after signing in with a one-time PIN, it is not asked for again
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const weak = pinWeakness(next);
    if (weak) return setError(t(weak));
    setBusy(true);
    try {
      await api.post("/v1/auth/change-pin", {
        current_pin: current,
        new_pin: next,
      });
      await api.renew(); // the access token from sign-in still holds every request for the PIN change
      pinChanged(next);
      router.replace("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <Title>{t("pin.change")}</Title>
      <Body>{t("signIn.mustChange")}</Body>
      {signInPin === null && (
        <Field
          label={t("pin.current")}
          value={typed}
          onChangeText={(v) => setTyped(v.replace(/\D/g, "").slice(0, 6))}
          keyboardType="number-pad"
          secureTextEntry
        />
      )}
      <Field testID="new-pin" label={t("pin.new")} value={next} onChangeText={(v) => setNext(v.replace(/\D/g, "").slice(0, 6))} keyboardType="number-pad" secureTextEntry />
      <ErrorText message={error} />
      <Button label={t("app.save")} busy={busy} disabled={current.length !== 6 || next.length !== 6} onPress={() => void submit()} />
      {/* A learner who doesn't know the current PIN must not be trapped here: signing out lets them start over. */}
      <Button label={t("settings.signOut")} kind="ghost" icon="log-out-outline" onPress={() => void signOut().then(() => router.replace("/sign-in"))} />
    </Screen>
  );
}
