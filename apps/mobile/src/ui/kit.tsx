/** Small UI kit: one-thumb friendly sizes (≥ 48 px targets), accessible labels everywhere. */
import type { ReactNode } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View, type TextInputProps } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { colors, space } from "./theme";

export function Screen({ children, scroll = true }: { children: ReactNode; scroll?: boolean }) {
  const body = <View style={styles.body}>{children}</View>;
  return (
    <SafeAreaView style={styles.screen} edges={["top", "left", "right"]}>
      {scroll ? <ScrollView contentContainerStyle={styles.scroll}>{body}</ScrollView> : body}
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

export function ErrorText({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <Text accessibilityRole="alert" style={styles.error}>
      {message}
    </Text>
  );
}

export function Loading() {
  return <ActivityIndicator accessibilityLabel="Loading" style={{ marginTop: space(4) }} />;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.paper },
  scroll: { flexGrow: 1 },
  body: { flex: 1, padding: space(2), gap: space(2) },
  title: { fontSize: 26, fontWeight: "700", color: colors.ink },
  text: { fontSize: 16, lineHeight: 22, color: colors.ink },
  card: { backgroundColor: colors.card, borderRadius: 14, padding: space(2), gap: space(1), borderWidth: 1, borderColor: colors.border },
  button: { minHeight: 52, borderRadius: 12, alignItems: "center", justifyContent: "center", paddingHorizontal: space(2) },
  buttonText: { fontSize: 17, fontWeight: "600" },
  label: { fontSize: 14, color: colors.muted },
  input: { minHeight: 52, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: space(1.5), fontSize: 18, color: colors.ink },
  error: { color: colors.danger, fontSize: 15 },
});
