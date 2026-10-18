/** Design tokens: a warm "travel journal" look. Paper and ink, a harbour-blue accent, sunset highlights,
 * a soft display serif for headings and Inter for everything else (decision 0016). */
import { Platform, type TextStyle, type ViewStyle } from "react-native";

export const colors = {
  ink: "#16213A",
  inkSoft: "#3B4660",
  paper: "#F6F1E9",
  paperDeep: "#EDE5D8",
  muted: "#737B8C",
  accent: "#1F5FAE",
  accentDeep: "#163F7A",
  accentSoft: "#E3ECF8",
  accentInk: "#FFFFFF",
  sunset: "#E9784F",
  sunsetSoft: "#FCE8DF",
  danger: "#B42318",
  dangerSoft: "#FDE7E4",
  success: "#1E7A4E",
  successSoft: "#E1F2E8",
  warning: "#B7791F",
  warningSoft: "#FBF0DC",
  card: "#FFFFFF",
  border: "#E8E0D2",
  overlay: "rgba(22, 33, 58, 0.55)",
} as const;

/** Hero gradients (Today card, sign-in). */
export const gradients = {
  dusk: ["#1F5FAE", "#163F7A"] as const,
  sunrise: ["#F3A26D", "#E9784F"] as const,
};

export const space = (n: number): number => n * 8;

/** Widest content column, so the web and iPad read like a phone app rather than a stretched form. */
export const MAX_WIDTH = 720;

export const radius = { sm: 10, md: 14, lg: 20, xl: 28, pill: 999 } as const;

/** Loaded in the root layout (expo-font); until then the system fonts stand in. */
export const fonts = {
  display: "Fraunces_600SemiBold",
  displayBold: "Fraunces_700Bold",
  body: "Inter_400Regular",
  medium: "Inter_500Medium",
  semibold: "Inter_600SemiBold",
  bold: "Inter_700Bold",
} as const;

export const type = {
  largeTitle: { fontFamily: fonts.displayBold, fontSize: 34, lineHeight: 40, color: colors.ink, letterSpacing: -0.4 },
  title: { fontFamily: fonts.display, fontSize: 24, lineHeight: 30, color: colors.ink, letterSpacing: -0.2 },
  headline: { fontFamily: fonts.semibold, fontSize: 17, lineHeight: 22, color: colors.ink },
  body: { fontFamily: fonts.body, fontSize: 16, lineHeight: 23, color: colors.ink },
  callout: { fontFamily: fonts.medium, fontSize: 15, lineHeight: 20, color: colors.inkSoft },
  caption: { fontFamily: fonts.medium, fontSize: 13, lineHeight: 17, color: colors.muted },
  overline: { fontFamily: fonts.semibold, fontSize: 12, lineHeight: 16, color: colors.muted, letterSpacing: 0.8, textTransform: "uppercase" },
} satisfies Record<string, TextStyle>;

/** Soft, warm elevation instead of hard borders. */
export const shadow = (level: 1 | 2 | 3 = 1): ViewStyle =>
  Platform.select<ViewStyle>({
    web: { boxShadow: `0 ${level * 2}px ${level * 10}px rgba(22, 33, 58, ${0.05 + level * 0.025})` } as ViewStyle,
    default: {
      shadowColor: "#16213A",
      shadowOpacity: 0.05 + level * 0.03,
      shadowRadius: level * 8,
      shadowOffset: { width: 0, height: level * 3 },
      elevation: level * 2,
    },
  }) ?? {};
