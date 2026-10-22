/** Where a sound is made, drawn: vowels on the tongue chart (how high, how far forward), consonants on the path from the
 * lips to the throat. When the learner said something else, it is drawn too, with an arrow toward the target, so
 * "move your tongue forward" can be seen as well as read. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { useTranslation } from "react-i18next";
import { StyleSheet, Text, View } from "react-native";

import { colors, fonts, radius, space, type } from "@/ui/theme";

import type { Features } from "./types";

const W = 200;
const H = 150;
const DOT = 30;
const LABELS = 64;

/** A point on the vowel chart: a trapezoid narrowing toward the open vowels, as in the IPA chart. */
function vowelAt(height: number, back: number): { x: number; y: number } {
  const left = (height / 3) * 0.38 * W;
  return { x: left + (back / 2) * (W - left), y: (height / 3) * H };
}

type Vowel = Extract<Features, { kind: "vowel" }>;

function vowelOf(
  features: Features | undefined,
  all: Record<string, Features>,
): Vowel | null {
  if (!features) return null;
  if (features.kind === "vowel") return features;
  if (features.kind === "diphthong") {
    const from = all[features.from];
    return from?.kind === "vowel" ? from : null;
  }
  return null;
}

function Arrow({
  from,
  to,
}: {
  from: { x: number; y: number };
  to: { x: number; y: number };
}) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.hypot(dx, dy);
  if (length < DOT) return null;
  const angle = Math.atan2(dy, dx);
  return (
    <View
      pointerEvents="none"
      style={{
        position: "absolute",
        left: (from.x + to.x) / 2 - length / 2,
        top: (from.y + to.y) / 2 - 1,
        width: length,
        height: 2,
        backgroundColor: colors.warning,
        transform: [{ rotate: `${angle}rad` }],
      }}
    />
  );
}

function Dot({
  at,
  label,
  tone,
}: {
  at: { x: number; y: number };
  label: string;
  tone: "target" | "heard";
}) {
  const target = tone === "target";
  return (
    <View
      style={[
        styles.dot,
        { left: at.x - DOT / 2, top: at.y - DOT / 2 },
        target
          ? { backgroundColor: colors.accent }
          : {
              backgroundColor: colors.card,
              borderWidth: 2,
              borderColor: colors.warning,
            },
      ]}
    >
      <Text
        style={[
          styles.dotText,
          { color: target ? colors.accentInk : colors.warning },
        ]}
      >
        {label}
      </Text>
    </View>
  );
}

function VowelChart({
  target,
  phoneme,
  heard,
  all,
}: {
  target: Features;
  phoneme: string;
  heard?: string | null;
  all: Record<string, Features>;
}) {
  const { t } = useTranslation();
  const start = vowelOf(target, all);
  const end = target.kind === "diphthong" ? vowelOf(all[target.to], all) : null;
  const other = heard ? vowelOf(all[heard], all) : null;
  if (!start) return null;
  const at = vowelAt(start.height, start.back);
  return (
    <View style={{ gap: space(0.5), alignItems: "center" }}>
      <View style={[styles.axis, { marginLeft: LABELS }]}>
        <Text style={type.caption}>{t("gym.map.front")}</Text>
        <Text style={type.caption}>{t("gym.map.back")}</Text>
      </View>
      <View style={{ flexDirection: "row" }}>
        <View style={styles.side}>
          <Text style={[type.caption, styles.sideText]}>
            {t("gym.map.closed")}
          </Text>
          <Text style={[type.caption, styles.sideText]}>
            {t("gym.map.open")}
          </Text>
        </View>
        <View
          style={styles.chart}
          accessibilityLabel={t("gym.map.vowelA11y", { sound: phoneme })}
        >
          <View
            style={[styles.edge, { left: 0, top: 0, width: W, height: 1 }]}
          />
          <View
            style={[
              styles.edge,
              { left: 0.38 * W, top: H, width: W * 0.62, height: 1 },
            ]}
          />
          <View
            style={[styles.edge, { left: W, top: 0, width: 1, height: H }]}
          />
          <View
            style={[
              styles.edge,
              {
                left: 0.19 * W - Math.hypot(0.38 * W, H) / 2,
                top: H / 2,
                width: Math.hypot(0.38 * W, H),
                height: 1,
                transform: [{ rotate: `${Math.atan2(H, 0.38 * W)}rad` }],
              },
            ]}
          />
          {other && <Arrow from={vowelAt(other.height, other.back)} to={at} />}
          {end && <Arrow from={at} to={vowelAt(end.height, end.back)} />}
          {other && heard && (
            <Dot
              at={vowelAt(other.height, other.back)}
              label={heard}
              tone="heard"
            />
          )}
          {end && target.kind === "diphthong" && (
            <Dot
              at={vowelAt(end.height, end.back)}
              label={target.to}
              tone="target"
            />
          )}
          <Dot
            at={at}
            label={target.kind === "diphthong" ? target.from : phoneme}
            tone="target"
          />
        </View>
      </View>
      <View style={styles.chips}>
        {start.rounded ? (
          <Chip icon="ellipse-outline" text={t("gym.map.rounded")} />
        ) : (
          <Chip icon="remove-outline" text={t("gym.map.spread")} />
        )}
        {start.nasal && (
          <Chip icon="git-branch-outline" text={t("gym.map.nasal")} />
        )}
        {target.kind === "diphthong" && (
          <Chip icon="trending-up-outline" text={t("gym.map.glide")} />
        )}
      </View>
    </View>
  );
}

const PLACES = [
  "lips",
  "teeth",
  "ridge",
  "roof",
  "softPalate",
  "uvula",
  "throat",
] as const;
const PLACE_OF: Record<string, (typeof PLACES)[number]> = {
  bilabial: "lips",
  "labial-velar": "lips",
  labiodental: "teeth",
  dental: "teeth",
  alveolar: "ridge",
  postalveolar: "ridge",
  palatal: "roof",
  velar: "softPalate",
  uvular: "uvula",
  glottal: "throat",
};

function Chip({
  icon,
  text,
}: {
  icon:
    | "ellipse-outline"
    | "remove-outline"
    | "git-branch-outline"
    | "trending-up-outline"
    | "pulse"
    | "volume-mute-outline";
  text: string;
}) {
  return (
    <View style={styles.chip}>
      <Ionicons name={icon} size={13} color={colors.accentDeep} />
      <Text style={styles.chipText}>{text}</Text>
    </View>
  );
}

function ConsonantStrip({
  target,
  heard,
  all,
}: {
  target: Extract<Features, { kind: "consonant" }>;
  heard?: string | null;
  all: Record<string, Features>;
}) {
  const { t } = useTranslation();
  const place = PLACE_OF[target.place];
  const other = heard ? all[heard] : undefined;
  const otherPlace =
    other?.kind === "consonant" ? PLACE_OF[other.place] : undefined;
  return (
    <View style={{ gap: space(1) }}>
      <View style={styles.strip}>
        {PLACES.map((p) => {
          const here = p === place;
          const wrong = p === otherPlace && !here;
          return (
            <View
              key={p}
              style={[
                styles.place,
                here && styles.placeOn,
                wrong && styles.placeWrong,
              ]}
            >
              <Text
                style={[
                  styles.placeText,
                  here && { color: colors.accentInk },
                  wrong && { color: colors.warning },
                ]}
                numberOfLines={2}
              >
                {t(`gym.map.place.${p}`)}
              </Text>
            </View>
          );
        })}
      </View>
      <View style={styles.chips}>
        <Chip
          icon={target.voiced ? "pulse" : "volume-mute-outline"}
          text={t(target.voiced ? "gym.map.voiced" : "gym.map.voiceless")}
        />
        <Chip
          icon="ellipse-outline"
          text={t(`gym.map.manner.${target.manner}`)}
        />
        {other?.kind === "consonant" && other.voiced !== target.voiced && (
          <Chip
            icon="pulse"
            text={t(target.voiced ? "gym.map.addVoice" : "gym.map.dropVoice")}
          />
        )}
      </View>
    </View>
  );
}

export function MouthMap({
  phoneme,
  features,
  heard,
  all,
}: {
  phoneme: string;
  features: Features;
  heard?: string | null;
  all: Record<string, Features>;
}) {
  if (features.kind === "consonant")
    return <ConsonantStrip target={features} heard={heard} all={all} />;
  return (
    <VowelChart target={features} phoneme={phoneme} heard={heard} all={all} />
  );
}

const styles = StyleSheet.create({
  chart: { width: W, height: H, marginVertical: DOT / 2 },
  side: {
    width: LABELS,
    height: H + DOT,
    justifyContent: "space-between",
    paddingRight: space(1),
  },
  sideText: { textAlign: "right" },
  edge: { position: "absolute", backgroundColor: colors.border },
  axis: { width: W, flexDirection: "row", justifyContent: "space-between" },
  dot: {
    position: "absolute",
    width: DOT,
    height: DOT,
    borderRadius: DOT / 2,
    alignItems: "center",
    justifyContent: "center",
  },
  dotText: { fontFamily: fonts.semibold, fontSize: 14 },
  chips: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: space(0.75),
    justifyContent: "center",
  },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: colors.accentSoft,
    borderRadius: radius.pill,
    paddingHorizontal: space(1),
    paddingVertical: 3,
  },
  chipText: {
    fontFamily: fonts.medium,
    fontSize: 12,
    color: colors.accentDeep,
  },
  strip: { flexDirection: "row", gap: 3 },
  place: {
    flex: 1,
    minHeight: 44,
    borderRadius: radius.sm,
    backgroundColor: colors.paperDeep,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 2,
  },
  placeOn: { backgroundColor: colors.accent },
  placeWrong: {
    backgroundColor: colors.warningSoft,
    borderWidth: 1,
    borderColor: colors.warning,
  },
  placeText: {
    fontFamily: fonts.medium,
    fontSize: 10,
    textAlign: "center",
    color: colors.inkSoft,
  },
});
