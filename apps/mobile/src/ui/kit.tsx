/** UI kit: one-thumb friendly sizes (≥ 48 px targets), accessible labels everywhere, the tokens in theme.ts. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { router } from "expo-router";
import { useEffect, useRef, useState, type ComponentProps, type ReactNode, type Ref, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import {
  ActivityIndicator,
  I18nManager,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type ViewStyle,
} from "react-native";
import Animated, { cancelAnimation, useAnimatedStyle, useSharedValue, withRepeat, withTiming } from "react-native-reanimated";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import { useOnline } from "@/api/connection";
import { colors, fonts, MAX_WIDTH, radius, shadow, space, type } from "./theme";

export type IconName = ComponentProps<typeof Ionicons>["name"];

/** Whether the on-screen keyboard is up, to make room for a form (e.g. fold away a header). */
export function useKeyboardVisible(): boolean {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const show = Keyboard.addListener(Platform.OS === "ios" ? "keyboardWillShow" : "keyboardDidShow", () => setVisible(true));
    const hide = Keyboard.addListener(Platform.OS === "ios" ? "keyboardWillHide" : "keyboardDidHide", () => setVisible(false));
    return () => {
      show.remove();
      hide.remove();
    };
  }, []);
  return visible;
}

/** Leave a pushed screen; a pasted link or a reload has nothing to go back to, so it goes home instead. */
export function goBack(): void {
  if (router.canGoBack()) router.back();
  else router.replace("/");
}

interface ScreenProps {
  children: ReactNode;
  scroll?: boolean;
  /** Large page title, iOS style (tab screens). */
  title?: string;
  /** A line above the title (a greeting, a date, a section name). */
  eyebrow?: string;
  /** Pushed screens get a back bar; tab screens don't. */
  back?: boolean;
  /** Overrides what the back button does, e.g. to leave a live scene first. */
  onBack?: () => void;
  /** Pull to refresh (scrolling screens only). */
  onRefresh?: () => Promise<unknown> | void;
  /** Controls pinned under the scrolling content, always in reach (a live scene's Leave and Hold to talk). */
  footer?: ReactNode;
  /** Keep the newest content in view as it grows (live captions). */
  followContent?: boolean;
  /** For a screen that scrolls itself to a part of its content (a lesson's games once practice starts). */
  scroller?: RefObject<ScrollView | null>;
}

export function Screen({ children, scroll = true, title, eyebrow, back = false, onBack, onRefresh, footer, followContent = false, scroller: given }: ScreenProps) {
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const own = useRef<ScrollView>(null);
  const scroller = given ?? own;
  const [refreshing, setRefreshing] = useState(false);
  const refresh = onRefresh
    ? () => {
        setRefreshing(true);
        void Promise.resolve(onRefresh()).finally(() => setRefreshing(false));
      }
    : undefined;
  const body = (
    <View style={styles.body}>
      {(title || eyebrow) && (
        <View style={styles.header}>
          {eyebrow ? <Text style={type.overline}>{eyebrow}</Text> : null}
          {title ? (
            <Text accessibilityRole="header" style={type.largeTitle}>
              {title}
            </Text>
          ) : null}
        </View>
      )}
      {children}
    </View>
  );
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
            <Ionicons name={I18nManager.isRTL ? "chevron-forward" : "chevron-back"} size={24} color={colors.accent} />
            <Text style={styles.backText}>{t("app.back")}</Text>
          </Pressable>
        </View>
      )}
      {/* Scroll views inset themselves for the keyboard; the avoiding view lifts unscrolled screens and footers. */}
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" && (!scroll || footer) ? "padding" : undefined}>
        {scroll ? (
          <ScrollView
            ref={scroller}
            onContentSizeChange={followContent ? () => scroller.current?.scrollToEnd({ animated: true }) : undefined}
            contentContainerStyle={styles.scroll}
            keyboardShouldPersistTaps="handled"
            keyboardDismissMode="interactive"
            automaticallyAdjustKeyboardInsets
            showsVerticalScrollIndicator={false}
            refreshControl={refresh ? <RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.muted} /> : undefined}
          >
            {body}
          </ScrollView>
        ) : (
          body
        )}
        {footer && <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, space(2)) }]}>{footer}</View>}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

/** A card or section heading, in the display serif. */
export function Title({ children }: { children: ReactNode }) {
  return (
    <Text accessibilityRole="header" style={type.title}>
      {children}
    </Text>
  );
}

export function Heading({ children }: { children: ReactNode }) {
  return <Text style={type.headline}>{children}</Text>;
}

export function Body({ children, muted = false }: { children: ReactNode; muted?: boolean }) {
  return <Text style={muted ? [type.callout, { color: colors.muted }] : type.body}>{children}</Text>;
}

export function Caption({ children }: { children: ReactNode }) {
  return <Text style={type.caption}>{children}</Text>;
}

export function Overline({ children }: { children: ReactNode }) {
  return <Text style={type.overline}>{children}</Text>;
}

type Tone = "plain" | "accent" | "sunset" | "success" | "warning" | "danger";
const TONES: Record<Tone, { background: string; ink: string }> = {
  plain: { background: colors.card, ink: colors.ink },
  accent: { background: colors.accentSoft, ink: colors.accentDeep },
  sunset: { background: colors.sunsetSoft, ink: "#9A3E1E" },
  success: { background: colors.successSoft, ink: colors.success },
  warning: { background: colors.warningSoft, ink: colors.warning },
  danger: { background: colors.dangerSoft, ink: colors.danger },
};

export function Card({ children, tone = "plain", style }: { children: ReactNode; tone?: Tone; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.card, { backgroundColor: TONES[tone].background }, tone === "plain" && shadow(1), style]}>{children}</View>;
}

type ButtonKind = "primary" | "secondary" | "tinted" | "danger" | "ghost";

export function Button({
  label,
  onPress,
  disabled = false,
  busy = false,
  kind = "primary",
  compact = false,
  icon,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  busy?: boolean;
  /** primary: the one main action. secondary: a neutral choice. tinted: a quieter action. ghost: text only. */
  kind?: ButtonKind;
  /** Narrow chips in a row of choices (levels, times): less side padding. */
  compact?: boolean;
  icon?: IconName;
}) {
  const look = {
    primary: { background: colors.accent, ink: colors.accentInk },
    secondary: { background: colors.card, ink: colors.ink },
    tinted: { background: colors.accentSoft, ink: colors.accentDeep },
    danger: { background: colors.danger, ink: colors.accentInk },
    ghost: { background: "transparent", ink: colors.accent },
  }[kind];
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: disabled || busy, busy }}
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: look.background, opacity: disabled ? 0.45 : 1, transform: [{ scale: pressed ? 0.98 : 1 }] },
        kind === "primary" && shadow(1),
        kind === "secondary" && styles.outlined,
        pressed && kind !== "ghost" && { opacity: 0.88 },
        compact && { paddingHorizontal: space(0.5), minHeight: 46 },
      ]}
    >
      {busy ? (
        <ActivityIndicator color={look.ink} />
      ) : (
        <View style={styles.buttonInner}>
          {icon && <Ionicons name={icon} size={19} color={look.ink} />}
          <Text style={[styles.buttonText, { color: look.ink }]} numberOfLines={2}>
            {label}
          </Text>
        </View>
      )}
    </Pressable>
  );
}

export type ChoiceState = "idle" | "picked" | "right" | "wrong" | "dim";

/** One answer in a multiple-choice question: a letter badge and left-aligned text that reads like a sentence.
 * A pick shows at once ("picked") while it is checked; then the right one turns green, a wrong pick red, and the rest step back. */
export function Choice({ label, index, state = "idle", onPress }: { label: string; index: number; state?: ChoiceState; onPress?: () => void }) {
  const look = {
    idle: { background: colors.card, border: colors.border, badge: colors.paper, badgeInk: colors.inkSoft, ink: colors.ink },
    picked: { background: colors.accentSoft, border: colors.accent, badge: colors.accent, badgeInk: "#fff", ink: colors.ink },
    right: { background: colors.successSoft, border: colors.success, badge: colors.success, badgeInk: "#fff", ink: colors.ink },
    wrong: { background: colors.dangerSoft, border: colors.danger, badge: colors.danger, badgeInk: "#fff", ink: colors.ink },
    dim: { background: colors.card, border: colors.border, badge: colors.paper, badgeInk: colors.muted, ink: colors.muted },
  }[state];
  const mark = state === "right" ? "checkmark" : state === "wrong" ? "close" : null;
  return (
    <Pressable
      testID={`choice-${index}`}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !onPress, selected: state === "right" || state === "wrong" }}
      disabled={!onPress}
      onPress={onPress}
      style={({ pressed }) => [
        styles.choice,
        { backgroundColor: look.background, borderColor: look.border, transform: [{ scale: pressed ? 0.985 : 1 }] },
        pressed && { backgroundColor: colors.accentSoft, borderColor: colors.accent },
      ]}
    >
      <View style={[styles.choiceBadge, { backgroundColor: look.badge }]}>
        {mark ? (
          <Ionicons name={mark} size={16} color={look.badgeInk} />
        ) : (
          <Text style={{ fontFamily: fonts.semibold, fontSize: 14, color: look.badgeInk }}>{String.fromCharCode(65 + index)}</Text>
        )}
      </View>
      <Text style={[type.body, { flex: 1, color: look.ink }]}>{label}</Text>
    </Pressable>
  );
}

/** A tappable row: icon or avatar, title, subtitle, and a chevron (places, settings, lessons). */
export function ListRow({
  title,
  subtitle,
  icon,
  leading,
  onPress,
  selected = false,
  trailing,
  disabled = false,
}: {
  title: string;
  subtitle?: string;
  icon?: IconName;
  leading?: ReactNode;
  onPress?: () => void;
  selected?: boolean;
  trailing?: ReactNode;
  disabled?: boolean;
}) {
  const content = (
    <>
      {leading ?? (icon && <IconBubble name={icon} tone={selected ? "accent" : "plain"} />)}
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[type.headline, disabled && { color: colors.muted }]} numberOfLines={2}>
          {title}
        </Text>
        {subtitle ? <Text style={type.caption}>{subtitle}</Text> : null}
      </View>
      {trailing ?? (onPress && <Ionicons name={I18nManager.isRTL ? "chevron-back" : "chevron-forward"} size={18} color={colors.muted} />)}
    </>
  );
  if (!onPress) return <View style={[styles.row, disabled && { opacity: 0.6 }]}>{content}</View>;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={subtitle ? `${title}, ${subtitle}` : title}
      accessibilityState={{ selected, disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [styles.row, selected && styles.rowSelected, pressed && { backgroundColor: colors.paperDeep }]}
    >
      {content}
    </Pressable>
  );
}

/** Rows grouped on one card with hairline separators, iOS-settings style. */
export function Section({ title, children, footer }: { title?: string; children: ReactNode; footer?: string }) {
  const rows = (Array.isArray(children) ? children : [children]).flat().filter(Boolean) as ReactNode[];
  return (
    <View style={{ gap: space(1) }}>
      {title ? <Text style={[type.overline, { marginLeft: space(1) }]}>{title}</Text> : null}
      {rows.length > 0 && (
        <View style={[styles.section, shadow(1)]}>
          {rows.map((row, i) => (
            <View key={i}>
              {i > 0 && <View style={styles.separator} />}
              {row}
            </View>
          ))}
        </View>
      )}
      {footer ? <Text style={[type.caption, { marginHorizontal: space(1) }]}>{footer}</Text> : null}
    </View>
  );
}

export function IconBubble({ name, tone = "plain", size = 40 }: { name: IconName; tone?: Tone; size?: number }) {
  const look = tone === "plain" ? { background: colors.paper, ink: colors.accent } : TONES[tone];
  return (
    <View style={[styles.bubble, { width: size, height: size, borderRadius: size / 2.6, backgroundColor: look.background }]}>
      <Ionicons name={name} size={size * 0.5} color={look.ink} />
    </View>
  );
}

const AVATAR_COLOURS = ["#1F5FAE", "#E9784F", "#1E7A4E", "#7A4FB0", "#B7791F", "#2C7A8C"];

/** A person's initials on a colour that stays the same for the same name. */
export function Avatar({ name, size = 40 }: { name: string; size?: number }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
  const colour = AVATAR_COLOURS[[...name].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7) % AVATAR_COLOURS.length];
  return (
    <View accessible={false} style={[styles.bubble, { width: size, height: size, borderRadius: size / 2, backgroundColor: colour }]}>
      <Text style={{ fontFamily: fonts.semibold, color: "#fff", fontSize: size * 0.38 }}>{initials}</Text>
    </View>
  );
}

export function Chip({ label, tone = "plain", icon }: { label: string; tone?: Tone; icon?: IconName }) {
  const look = tone === "plain" ? { background: colors.paper, ink: colors.inkSoft } : TONES[tone];
  return (
    <View style={[styles.chip, { backgroundColor: look.background }]}>
      {icon && <Ionicons name={icon} size={13} color={look.ink} />}
      <Text style={[type.caption, { color: look.ink, fontFamily: fonts.semibold }]}>{label}</Text>
    </View>
  );
}

/** Progress towards a goal, 0–1. */
export function ProgressBar({ value, tone = "accent" }: { value: number; tone?: Tone }) {
  const fill = { accent: colors.accent, sunset: colors.sunset, success: colors.success, warning: colors.warning, danger: colors.danger, plain: colors.muted }[tone];
  return (
    <View style={styles.track} accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 100, now: Math.round(value * 100) }}>
      <View style={[styles.fill, { width: `${Math.max(0, Math.min(1, value)) * 100}%`, backgroundColor: fill }]} />
    </View>
  );
}

/** One choice out of a few (city, language): a pill track with the chosen option raised. */
export function Segmented<T extends string>({ options, value, onChange }: { options: { value: T; label: string }[]; value: T | null; onChange: (v: T) => void }) {
  return (
    <View style={styles.segmented} accessibilityRole="tablist">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <Pressable
            key={o.value}
            accessibilityRole="tab"
            accessibilityLabel={o.label}
            accessibilityState={{ selected: on }}
            onPress={() => onChange(o.value)}
            style={[styles.segment, on && [styles.segmentOn, shadow(1)]]}
          >
            <Text style={[type.headline, { color: on ? colors.ink : colors.muted, fontSize: 15 }]} numberOfLines={1}>
              {o.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function Field(props: TextInputProps & { label: string; ref?: Ref<TextInput> }) {
  const { label, style, ...rest } = props;
  const [focused, setFocused] = useState(false);
  return (
    <View style={{ gap: space(0.75) }}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor={colors.muted}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        style={[styles.input, focused && styles.inputFocused, style]}
        {...rest}
      />
    </View>
  );
}

/** An error, with a way out when one exists: never leave the learner staring at a dead end. */
/** An error where it happened. While the server can't be reached the connection banner speaks for every screen, so
 * error boxes stay quiet rather than each saying it again. */
export function ErrorText({ message, onRetry }: { message: string | null | undefined; onRetry?: () => void }) {
  const { t } = useTranslation();
  const online = useOnline();
  if (!message || !online) return null;
  return (
    <View style={styles.errorBox}>
      <View style={{ flexDirection: "row", gap: space(1), alignItems: "flex-start" }}>
        <Ionicons name="alert-circle" size={20} color={colors.danger} />
        <Text accessibilityRole="alert" style={[type.callout, { color: colors.danger, flex: 1 }]}>
          {message}
        </Text>
      </View>
      {onRetry && <Button label={t("app.retry")} kind="secondary" icon="refresh" onPress={onRetry} />}
    </View>
  );
}

/** While a screen loads: soft placeholder cards that breathe, in the shape of what is coming, instead of a lone
 * spinner. ``inline`` is a small spinner for places inside a card. */
export function Loading({ inline = false }: { inline?: boolean }) {
  const { t } = useTranslation();
  const pulse = useSharedValue(0);
  useEffect(() => {
    if (!inline) pulse.set(withRepeat(withTiming(1, { duration: 800 }), -1, true));
    return () => cancelAnimation(pulse);
  }, [inline, pulse]);
  const breathe = useAnimatedStyle(() => ({ opacity: 0.55 + 0.45 * pulse.value }));
  if (inline) return <ActivityIndicator accessibilityLabel={t("app.loading")} color={colors.accent} style={{ marginVertical: space(2) }} />;
  return (
    <Animated.View style={[{ gap: space(1.5) }, breathe]} accessible accessibilityLabel={t("app.loading")} accessibilityRole="progressbar">
      {[0.6, 1, 0.8].map((width, i) => (
        <View key={i} style={styles.skeleton}>
          <View style={[styles.skeletonLine, { width: `${width * 55}%`, height: 18 }]} />
          <View style={[styles.skeletonLine, { width: `${width * 90}%` }]} />
          <View style={[styles.skeletonLine, { width: `${width * 70}%` }]} />
        </View>
      ))}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  skeleton: { backgroundColor: colors.card, borderRadius: radius.lg, padding: space(2.5), gap: space(1.25) },
  skeletonLine: { height: 12, borderRadius: 6, backgroundColor: colors.paperDeep },
  screen: { flex: 1, backgroundColor: colors.paper },
  flex: { flex: 1 },
  scroll: { flexGrow: 1, paddingBottom: space(4) },
  // One readable column on wide screens (web, iPad); full width on phones.
  body: { flex: 1, width: "100%", maxWidth: MAX_WIDTH, alignSelf: "center", paddingHorizontal: space(2.5), paddingTop: space(1), gap: space(2) },
  header: { gap: space(0.5), marginTop: space(1), marginBottom: space(0.5) },
  bar: { width: "100%", maxWidth: MAX_WIDTH, alignSelf: "center", paddingHorizontal: space(1.5), minHeight: 44, justifyContent: "center" },
  backButton: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", minHeight: 44, paddingRight: space(1), gap: 2 },
  backText: { fontFamily: fonts.medium, fontSize: 17, color: colors.accent },
  footer: {
    width: "100%",
    maxWidth: MAX_WIDTH,
    alignSelf: "center",
    paddingHorizontal: space(2.5),
    paddingTop: space(1.5),
    gap: space(1),
    backgroundColor: colors.paper,
  },
  card: { borderRadius: radius.lg, padding: space(2.5), gap: space(1.25) },
  button: { minHeight: 54, borderRadius: radius.md, alignItems: "center", justifyContent: "center", paddingHorizontal: space(2.5) },
  outlined: { borderWidth: 1, borderColor: colors.border },
  buttonInner: { flexDirection: "row", alignItems: "center", gap: space(1) },
  buttonText: { fontFamily: fonts.semibold, fontSize: 16, textAlign: "center" },
  choice: {
    flexDirection: "row",
    alignItems: "center",
    gap: space(1.5),
    minHeight: 54,
    borderRadius: radius.md,
    borderWidth: 1.5,
    paddingVertical: space(1.25),
    paddingHorizontal: space(1.5),
  },
  choiceBadge: { width: 28, height: 28, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  row: { flexDirection: "row", alignItems: "center", gap: space(1.5), paddingVertical: space(1.5), paddingHorizontal: space(2), minHeight: 64, backgroundColor: colors.card },
  rowSelected: { backgroundColor: colors.accentSoft },
  section: { backgroundColor: colors.card, borderRadius: radius.lg, overflow: "hidden" },
  separator: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border, marginLeft: space(2) },
  bubble: { alignItems: "center", justifyContent: "center" },
  chip: { flexDirection: "row", alignItems: "center", gap: 4, borderRadius: radius.pill, paddingHorizontal: space(1.25), paddingVertical: 5 },
  track: { height: 8, borderRadius: radius.pill, backgroundColor: colors.paperDeep, overflow: "hidden" },
  fill: { height: "100%", borderRadius: radius.pill },
  segmented: { flexDirection: "row", backgroundColor: colors.paperDeep, borderRadius: radius.md, padding: 4, gap: 4 },
  segment: { flex: 1, minHeight: 44, borderRadius: radius.sm, alignItems: "center", justifyContent: "center", paddingHorizontal: space(1) },
  segmentOn: { backgroundColor: colors.card },
  label: { ...type.overline },
  input: {
    minHeight: 54,
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.card,
    paddingHorizontal: space(2),
    fontSize: 17,
    fontFamily: fonts.body,
    color: colors.ink,
  },
  inputFocused: { borderColor: colors.accent },
  errorBox: { backgroundColor: colors.dangerSoft, borderRadius: radius.md, padding: space(2), gap: space(1.5) },
});
