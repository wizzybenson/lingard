import { Redirect } from "expo-router";

import { useAuth } from "@/state/auth";
import { Loading, Screen } from "@/ui/kit";

export default function Index() {
  const { status, pinChangeRequired } = useAuth();
  if (status === "booting") {
    return (
      <Screen>
        <Loading inline />
      </Screen>
    );
  }
  if (status !== "signedIn") return <Redirect href="/sign-in" />;
  if (pinChangeRequired) return <Redirect href="/change-pin" />;
  return <Redirect href="/(tabs)/city" />;
}
