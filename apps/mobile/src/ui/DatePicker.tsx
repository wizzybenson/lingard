/** A date field that opens a month calendar: no typing formats, the learner's own language for month and day
 * names, past days greyed out. Values are ISO dates (YYYY-MM-DD), as the API stores them. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { I18nManager, Pressable, StyleSheet, Text, View } from "react-native";

import { colors, fonts, radius, space, type } from "./theme";

export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function parseIso(value: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!m) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return d.getMonth() === Number(m[2]) - 1 ? d : null;
}

/** The weeks of a month, Monday first, as day numbers with ``null`` padding. */
export function monthGrid(year: number, month: number): (number | null)[][] {
  const first = (new Date(year, month, 1).getDay() + 6) % 7;
  const days = new Date(year, month + 1, 0).getDate();
  const cells: (number | null)[] = [...Array<null>(first).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  while (cells.length % 7) cells.push(null);
  return Array.from({ length: cells.length / 7 }, (_, w) => cells.slice(w * 7, w * 7 + 7));
}

export function DatePicker({ label, value, onChange, today = new Date() }: { label: string; value: string; onChange: (iso: string) => void; today?: Date }) {
  const { i18n } = useTranslation();
  const chosen = parseIso(value);
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState(() => {
    const base = chosen ?? today;
    return { year: base.getFullYear(), month: base.getMonth() };
  });
  const locale = i18n.language;
  const long = new Intl.DateTimeFormat(locale, { day: "numeric", month: "long", year: "numeric" });
  const monthName = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }).format(new Date(shown.year, shown.month, 1));
  const weekdays = Array.from({ length: 7 }, (_, i) => new Intl.DateTimeFormat(locale, { weekday: "narrow" }).format(new Date(2024, 0, 1 + i)));
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const step = (delta: number) =>
    setShown(({ year, month }) => {
      const d = new Date(year, month + delta, 1);
      return { year: d.getFullYear(), month: d.getMonth() };
    });

  return (
    <View style={{ gap: space(0.75) }}>
      <Text style={type.overline}>{label}</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${label}: ${chosen ? long.format(chosen) : "—"}`}
        onPress={() => setOpen((o) => !o)}
        style={[styles.field, open && styles.fieldOpen]}
      >
        <Ionicons name="calendar" size={20} color={colors.accent} />
        <Text style={[type.body, { flex: 1, color: chosen ? colors.ink : colors.muted }]}>{chosen ? long.format(chosen) : "—"}</Text>
        <Ionicons name={open ? "chevron-up" : "chevron-down"} size={18} color={colors.muted} />
      </Pressable>
      {open && (
        <View style={styles.calendar}>
          <View style={styles.header}>
            <Pressable accessibilityRole="button" accessibilityLabel="‹" hitSlop={10} onPress={() => step(-1)} style={styles.arrow}>
              <Ionicons name={I18nManager.isRTL ? "chevron-forward" : "chevron-back"} size={22} color={colors.accent} />
            </Pressable>
            <Text style={[type.headline, { flex: 1, textAlign: "center", textTransform: "capitalize" }]}>{monthName}</Text>
            <Pressable accessibilityRole="button" accessibilityLabel="›" hitSlop={10} onPress={() => step(1)} style={styles.arrow}>
              <Ionicons name={I18nManager.isRTL ? "chevron-back" : "chevron-forward"} size={22} color={colors.accent} />
            </Pressable>
          </View>
          <View style={styles.week}>
            {weekdays.map((d, i) => (
              <Text key={i} style={[type.caption, styles.cell, { textAlign: "center" }]}>
                {d}
              </Text>
            ))}
          </View>
          {monthGrid(shown.year, shown.month).map((week, w) => (
            <View key={w} style={styles.week}>
              {week.map((day, i) => {
                if (day === null) return <View key={i} style={styles.cell} />;
                const date = new Date(shown.year, shown.month, day);
                const past = date < start;
                const on = chosen !== null && isoDate(chosen) === isoDate(date);
                return (
                  <Pressable
                    key={i}
                    accessibilityRole="button"
                    accessibilityLabel={long.format(date)}
                    accessibilityState={{ selected: on, disabled: past }}
                    disabled={past}
                    onPress={() => {
                      onChange(isoDate(date));
                      setOpen(false);
                    }}
                    style={[styles.cell, styles.day, on && styles.dayOn]}
                  >
                    <Text style={[styles.dayText, past && { color: colors.border }, on && { color: colors.accentInk }]}>{day}</Text>
                  </Pressable>
                );
              })}
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  field: {
    flexDirection: "row",
    alignItems: "center",
    gap: space(1.25),
    minHeight: 54,
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.card,
    paddingHorizontal: space(2),
  },
  fieldOpen: { borderColor: colors.accent },
  calendar: { borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: space(1.5), gap: 4 },
  header: { flexDirection: "row", alignItems: "center", marginBottom: space(1) },
  arrow: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  week: { flexDirection: "row" },
  cell: { flex: 1, aspectRatio: 1, maxHeight: 48 },
  day: { alignItems: "center", justifyContent: "center", borderRadius: radius.pill },
  dayOn: { backgroundColor: colors.accent },
  dayText: { fontFamily: fonts.medium, fontSize: 16, color: colors.ink },
});
