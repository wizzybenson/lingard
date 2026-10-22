import "@/i18n";

import { Fraunces_600SemiBold, Fraunces_700Bold } from "@expo-google-fonts/fraunces";
import { Inter_400Regular, Inter_500Medium, Inter_600SemiBold, Inter_700Bold, useFonts } from "@expo-google-fonts/inter";
import { Stack, router, useSegments } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { Platform } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { AuthProvider, useAuth } from "@/state/auth";
import { ConnectionBanner } from "@/ui/ConnectionBanner";
import { colors } from "@/ui/theme";

const PUBLIC = new Set(["sign-in", "index"]);

/** Every screen except sign-in needs a session. A reload or pasted link without one (or with a stale PIN) lands here
 * signed out and must go to sign-in rather than show "Not signed in". */
function AuthGate() {
  const { status } = useAuth();
  const segments = useSegments();
  const first = segments[0] ?? "index";
  useEffect(() => {
    if ((status === "signedOut" || status === "locked") && !PUBLIC.has(first)) router.replace("/sign-in");
  }, [status, first]);
  return null;
}

export default function RootLayout() {
  // Web: CanvasKit (Skia for the web) must be loaded before any Skia component renders.
  // Phones: livekit-client needs the native WebRTC globals before a scene creates its room.
  const [ready, setReady] = useState(false);
  // Font failures fall back to the system fonts rather than blocking the app.
  const [fontsLoaded, fontError] = useFonts({
    Fraunces_600SemiBold,
    Fraunces_700Bold,
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
    Inter_700Bold,
  });
  useEffect(() => {
    if (Platform.OS === "web") {
      void import("@shopify/react-native-skia/lib/module/web")
        .then((m) => m.LoadSkiaWeb({ locateFile: (file: string) => `/${file}` }))
        .then(() => setReady(true));
    } else {
      // Without WebRTC only live scenes fail (with their own error); everything else still works.
      void import("@livekit/react-native").then((m) => m.registerGlobals()).finally(() => setReady(true));
    }
  }, []);
  if (!ready || !(fontsLoaded || fontError)) return null;
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <AuthProvider>
          <AuthGate />
          <StatusBar style="dark" />
          <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.paper } }}>
            {/* A verb's tables slide up over the lesson or brief that opened them, which stays right underneath. */}
            <Stack.Screen
              name="verb/[language]/[key]"
              options={{
                presentation: "formSheet",
                sheetAllowedDetents: [0.7, 1],
                sheetGrabberVisible: true,
                sheetCornerRadius: 28,
                contentStyle: { backgroundColor: colors.paper },
              }}
            />
          </Stack>
          <ConnectionBanner />
        </AuthProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
