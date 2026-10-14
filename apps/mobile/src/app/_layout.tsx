import "@/i18n";

import { Stack, router, useSegments } from "expo-router";
import { useEffect, useState } from "react";
import { Platform } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { AuthProvider, useAuth } from "@/state/auth";

const PUBLIC = new Set(["sign-in", "index"]);

/** Every screen except sign-in needs a session. On the web tokens live in memory only, so a reload or a pasted
 * link lands here signed out and must go to sign-in rather than show "Not signed in". */
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
  const [ready, setReady] = useState(Platform.OS !== "web");
  useEffect(() => {
    if (Platform.OS === "web") {
      // CanvasKit (Skia for the web) must be loaded before any Skia component renders.
      void import("@shopify/react-native-skia/lib/module/web")
        .then((m) => m.LoadSkiaWeb({ locateFile: (file: string) => `/${file}` }))
        .then(() => setReady(true));
    }
  }, []);
  useEffect(() => {
    if (Platform.OS !== "web") {
      // Native WebRTC globals for livekit-client (no-op on web, where the browser provides them).
      void import("@livekit/react-native").then((m) => m.registerGlobals());
    }
  }, []);
  if (!ready) return null;
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <AuthProvider>
          <AuthGate />
          <Stack screenOptions={{ headerShown: false }} />
        </AuthProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
