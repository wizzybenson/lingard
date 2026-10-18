/** Small UI kit: one-thumb friendly sizes (≥ 48 px targets), accessible labels everywhere. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { router } from "expo-router";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  ActivityIndicator,
  I18nManager,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type TextInputProps,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { colors, MAX_WIDTH, space } from "./theme";

/** Leave a pushed screen; a pasted link or a reload has nothing to go back to, so it goes home instead. */
export function goBack(): void {
  if (router.canGoBack()) router.back();
  else router.replace("/");
}

interface ScreenProps {
  children: ReactNode;
  scroll?: boolean;
  /** Pushed screens get a back bar; tab screens don't. */
  back?: boolean;
  /** Overrides what the back button does, e.g. to leave a live scene first. */
  onBack?: () => void;
  /** Pull to refresh (scrolling screens only). */
  onRefresh?: () => Promise<unknown> | void;
}

export function Screen({ children, scroll = true, back = false, onBack, onRefresh }: ScreenProps) {
  const { t } = useTranslation();
  const [refreshing, setRefreshing] = useState(false);
  const refresh = onRefresh
    ? () => {
        setRefreshing(true);
        void Promise.resolve(onRefresh()).finally(() => setRefreshing(false));
      }
    : undefined;
  const body = <View style={styles.body}>{children}</View>;
  return (
    <SafeAreaView style={styles.screen} edges={["top", "left", "right"]}>
      {back && (
        <View style={styles.bar}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t("app.back")}
            hitSlop={8}
            onPress={onBack ?? goBack}
            style={({ pressed }) => [styles.backButton, pressed && { opacity: 0.6 }]}
          >
            <Ionicons name={I18nManager.isRTL ? "chevron-forward" : "chevron-back"} size={26} color={colors.accent} />
            <Text style={styles.backText}>{t("app.back")}</Text>
          </Pressable>
        </View>
      )}
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        {scroll ? (
          <ScrollView
            contentContainerStyle={styles.scroll}
            keyboardShouldPersistTaps="handled"
            keyboardDismissMode="interactive"
            refreshControl={refresh ? <RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.muted} /> : undefined}
          >
            {body}
          </ScrollView>
        ) : (
          body
        )}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

export function Title({ children }: { children: ReactNode }) {
  return (
    <Text accessibilityRole="header" style={styles.title}>
      {children}
    </Text>
  );
}

export function Body({ children, muted = false }: { children: ReactNode; muted?: boolean }) {
  return <Text style={[styles.text, muted && { color: colors.muted }]}>{children}</Text>;
}

export function Card({ children }: { children: ReactNode }) {
  return <View style={styles.card}>{children}</View>;
}

export function Button({
  label,
  onPress,
  disabled = false,
  busy = false,
  kind = "primary",
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  busy?: boolean;
  kind?: "primary" | "secondary" | "danger";
}) {
  const background = kind === "primary" ? colors.accent : kind === "danger" ? colors.danger : colors.card;
  const ink = kind === "secondary" ? colors.ink : colors.accentInk;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: disabled || busy, busy }}
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: background, opacity: disabled ? 0.5 : pressed ? 0.85 : 1 },
        kind === "secondary" && { borderWidth: 1, borderColor: colors.border },
      ]}
    >
      {busy ? <ActivityIndicator color={ink} /> : <Text style={[styles.buttonText, { color: ink }]}>{label}</Text>}
    </Pressable>
  );
}

export function Field(props: TextInputProps & { label: string }) {
  const { label, style, ...rest } = props;
  return (
    <View style={{ gap: space(0.5) }}>
      <Text style={styles.label}>{label}</Text>
      <TextInput accessibilityLabel={label} placeholderTextColor={colors.muted} style={[styles.input, style]} {...rest} />
    </View>
  );
}

/** An error, with a way out when one exists: never leave the learner staring at a dead end. */
export function ErrorText({ message, onRetry }: { message: string | null | undefined; onRetry?: () => void }) {
  const { t } = useTranslation();
  if (!message) return null;
  return (
    <View style={{ gap: space(1) }}>
      <Text accessibilityRole="alert" style={styles.error}>
        {message}
      </Text>
      {onRetry && <Button label={t("app.retry")} kind="secondary" onPress={onRetry} />}
    </View>
  );
}

export function Loading() {
  const { t } = useTranslation();
  return <ActivityIndicator accessibilityLabel={t("app.loading")} style={{ marginTop: space(4) }} />;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.paper },
  flex: { flex: 1 },
  scroll: { flexGrow: 1, paddingBottom: space(3) },
  // One readable column on wide screens (web, iPad); full width on phones.
  body: { flex: 1, width: "100%", maxWidth: MAX_WIDTH, alignSelf: "center", padding: space(2), gap: space(2) },
  bar: { width: "100%", maxWidth: MAX_WIDTH, alignSelf: "center", paddingHorizontal: space(1), minHeight: 44, justifyContent: "center" },
  backButton: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", minHeight: 44, paddingRight: space(1) },
  backText: { fontSize: 17, color: colors.accent },
  title: { fontSize: 26, fontWeight: "700", color: colors.ink },
  text: { fontSize: 16, lineHeight: 22, color: colors.ink },
  card: { backgroundColor: colors.card, borderRadius: 14, padding: space(2), gap: space(1), borderWidth: 1, borderColor: colors.border },
  button: { minHeight: 52, borderRadius: 12, alignItems: "center", justifyContent: "center", paddingHorizontal: space(2) },
  buttonText: { fontSize: 17, fontWeight: "600" },
  label: { fontSize: 14, color: colors.muted },
  input: { minHeight: 52, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: space(1.5), fontSize: 18, color: colors.ink },
  error: { color: colors.danger, fontSize: 15 },
});
