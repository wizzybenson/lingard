import Ionicons from "@expo/vector-icons/Ionicons";
import { router, useFocusEffect } from "expo-router";
import { useCallback, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type { Passport, Profile, Wallet } from "@/api/types";
import { useApi } from "@/state/auth";
import { useCities } from "@/state/cities";
import { useResource } from "@/state/resource";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { levelProgress, levelWords } from "@/home/levels";
import { Body, Button, Caption, Card, Chip, Disclosure, ErrorText, ListRow, Loading, Overline, ProgressBar, Screen, Section, Title } from "@/ui/kit";
import { useFocus } from "@/state/focus";
import { colors, fonts, space, type } from "@/ui/theme";

interface DrawView {
  draw: {
    category: string;
    held_at: string;
    cutoff: number;
    source_note: string;
  } | null;
  sim_crs?: number | null;
  invited?: boolean;
  reward?: number;
}

export default function PassportScreen() {
  const { t, i18n } = useTranslation();
  const api = useApi();
  const passport = useResource(() => api.get<Passport>("/v1/passport"));
  const wallet = useResource(() => api.get<Wallet>("/v1/wallet"));
  const profile = useResource(() => api.get<Profile>("/v1/me"));
  const draw = useResource(() => api.get<DrawView>("/v1/draws/latest"));
  const cities = useCities();
  const focus = useFocus();
  const packOf = (pack: string) => cities.data?.find((c) => c.pack === pack);
  const { reload: reloadPassport } = passport;
  const { reload: reloadWallet } = wallet;
  const { reload: reloadProfile } = profile;
  const { reload: reloadDraw } = draw;
  const reloadAll = useCallback(() => {
    reloadPassport();
    reloadWallet();
    reloadProfile();
    reloadDraw();
  }, [reloadPassport, reloadWallet, reloadProfile, reloadDraw]);
  useFocusEffect(reloadAll);
  return (
    <Screen
      title={t("passport.title")}
      onRefresh={reloadAll}
      accessory={
        <Pressable accessibilityRole="button" accessibilityLabel={t("tabs.settings")} hitSlop={10} onPress={() => router.push("/settings")}>
          <Ionicons name="settings-outline" size={24} color={colors.inkSoft} />
        </Pressable>
      }
    >
      {passport.loading && !passport.data && <Loading />}
      <ErrorText message={passport.error} onRetry={reloadAll} />
      {passport.data && (
        <Card>
          <Overline>{t("passport.simCrs")}</Overline>
          <View
            style={{
              flexDirection: "row",
              alignItems: "flex-end",
              justifyContent: "space-between",
              gap: space(2),
            }}
          >
            {passport.data.sim_crs === null ? (
              <Text style={[type.callout, { flex: 1 }]}>{t("passport.crsPending")}</Text>
            ) : (
              <Text
                style={{
                  fontFamily: fonts.displayBold,
                  fontSize: 48,
                  lineHeight: 54,
                  color: colors.ink,
                }}
              >
                {passport.data.sim_crs}
              </Text>
            )}
            {wallet.data && (
              <View
                style={{
                  flexDirection: "row",
                  gap: space(2),
                  paddingBottom: space(1),
                }}
              >
                <Stat icon="cash" value={wallet.data.coins} label={t("wallet.coins")} />
                <Stat icon="star" value={wallet.data.stars_total} label={t("wallet.stars")} />
              </View>
            )}
          </View>
          {wallet.data && <Button kind="tinted" icon="bag-handle" label={t("shop.open")} onPress={() => router.push("/shop")} />}
          {draw.data?.draw && (
            <View style={{ gap: space(0.75) }}>
              <View
                style={{
                  flexDirection: "row",
                  alignItems: "center",
                  gap: space(1),
                }}
              >
                <Ionicons name={draw.data.invited ? "mail-open" : "mail"} size={16} color={draw.data.invited ? colors.success : colors.accent} />
                <Text style={[type.callout, { flex: 1, color: colors.ink }]}>
                  {t(draw.data.invited ? "passport.drawInvited" : "passport.drawGoal", {
                    cutoff: draw.data.draw.cutoff,
                    category: t(`passport.drawCategory.${draw.data.draw.category}`),
                    date: new Date(draw.data.draw.held_at).toLocaleDateString(i18n.language, { day: "numeric", month: "long" }),
                    reward: draw.data.reward ?? 0,
                  })}
                </Text>
              </View>
              <ProgressBar value={Math.min(1, (draw.data.sim_crs ?? 0) / draw.data.draw.cutoff)} tone={draw.data.invited ? "success" : "accent"} />
            </View>
          )}
          <Caption>{t("passport.disclaimer")}</Caption>
        </Card>
      )}
      {passport.data && passport.data.bands.length === 0 && (
        <Card tone="accent">
          <Body>{t("passport.noData")}</Body>
        </Card>
      )}
      {passport.data &&
        // The exam in focus in full; any other folded to its name, so one exam's levels fill the page, not two.
        [...new Set(passport.data.bands.map((b) => b.pack))]
          .sort((x, y) => Number(y === focus.city?.pack) - Number(x === focus.city?.pack))
          .map((pack, index) => (
            <Fold key={pack} open={index === 0} title={packOf(pack)?.pack_name ?? pack}>
              {index === 0 && packOf(pack)?.level_scale && <Caption>{t("today.levelsHint", { scale: packOf(pack)!.level_scale })}</Caption>}
              <Card style={{ gap: 0, paddingVertical: space(0.5) }}>
                {passport
                  .data!.bands.filter((b) => b.pack === pack)
                  .map((band, i) => {
                    const target = profile.data?.target_bands[band.pack]?.[band.skill];
                    const reach = target ? levelProgress(band.clb_nclc_low, band.clb_nclc_high, target) : 0;
                    return (
                      <View
                        key={`${band.pack}-${band.skill}`}
                        style={[
                          { gap: space(0.75), paddingVertical: space(1.5) },
                          i > 0 && {
                            borderTopWidth: StyleSheet.hairlineWidth,
                            borderTopColor: colors.border,
                          },
                        ]}
                      >
                        <View
                          style={{
                            flexDirection: "row",
                            justifyContent: "space-between",
                            alignItems: "center",
                            gap: space(1),
                            flexWrap: "wrap",
                          }}
                        >
                          <Text style={type.headline}>{t(`skills.${band.skill}`)}</Text>
                          {target !== undefined && <Chip label={t("today.goalLevel", { level: target })} tone="accent" icon="flag" />}
                        </View>
                        <ProgressBar value={reach} tone={reach >= 1 ? "success" : reach >= 0.8 ? "warning" : "accent"} />
                        <Text style={type.callout}>
                          {t("passport.levelEstimate", {
                            range: levelWords(t, band.clb_nclc_low, band.clb_nclc_high),
                          })}
                        </Text>
                        <Caption>
                          {t("passport.scoreEstimate", {
                            mean: band.mean,
                            low: band.low80,
                            high: band.high80,
                          })}
                        </Caption>
                      </View>
                    );
                  })}
              </Card>
            </Fold>
          ))}
      <Section>
        <ListRow icon="flag" title={t("settings.goal")} onPress={() => router.push("/goal")} />
        <ListRow icon="settings" title={t("tabs.settings")} testID="settings-row" onPress={() => router.push("/settings")} />
      </Section>
    </Screen>
  );
}

/** The exam in focus under its title; another exam folded to a line that opens. */
function Fold({ open, title, children }: { open: boolean; title: string; children: ReactNode }) {
  return open ? (
    <View style={{ gap: space(1.5) }}>
      <Title>{title}</Title>
      {children}
    </View>
  ) : (
    <Disclosure title={title}>
      <View style={{ gap: space(1.5) }}>{children}</View>
    </Disclosure>
  );
}

function Stat({ icon, value, label }: { icon: "cash" | "star"; value: number; label: string }) {
  return (
    <View style={{ alignItems: "center" }} accessible accessibilityLabel={`${label}: ${value}`}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
        <Ionicons name={icon} size={16} color={icon === "star" ? colors.warning : colors.sunset} />
        <Text style={type.headline}>{value}</Text>
      </View>
      <Caption>{label}</Caption>
    </View>
  );
}
