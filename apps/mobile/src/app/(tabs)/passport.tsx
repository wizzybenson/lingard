import Ionicons from "@expo/vector-icons/Ionicons";
import { router, useFocusEffect } from "expo-router";
import { useCallback } from "react";
import { useTranslation } from "react-i18next";

import type { Passport, Profile, Wallet } from "@/api/types";
import { useApi } from "@/state/auth";
import { useCities } from "@/state/cities";
import { useResource } from "@/state/resource";
import { Text, View } from "react-native";

import { levelProgress, levelWords } from "@/home/levels";
import { Body, Caption, Card, Chip, ErrorText, ListRow, Loading, Overline, ProgressBar, Screen, Section, Title } from "@/ui/kit";
import { colors, fonts, space, type } from "@/ui/theme";



export default function PassportScreen() {
  const { t } = useTranslation();
  const api = useApi();
  const passport = useResource(() => api.get<Passport>("/v1/passport"));
  const wallet = useResource(() => api.get<Wallet>("/v1/wallet"));
  const profile = useResource(() => api.get<Profile>("/v1/me"));
  const cities = useCities();
  const packOf = (pack: string) => cities.data?.find((c) => c.pack === pack);
  const { reload: reloadPassport } = passport;
  const { reload: reloadWallet } = wallet;
  const { reload: reloadProfile } = profile;
  const reloadAll = useCallback(() => {
    reloadPassport();
    reloadWallet();
    reloadProfile();
  }, [reloadPassport, reloadWallet, reloadProfile]);
  useFocusEffect(reloadAll);
  return (
    <Screen title={t("passport.title")} onRefresh={reloadAll}>
      {passport.loading && !passport.data && <Loading />}
      <ErrorText message={passport.error} onRetry={reloadAll} />
      {passport.data && (
        <Card>
          <Overline>{t("passport.simCrs")}</Overline>
          <View style={{ flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", gap: space(2) }}>
            <Text style={{ fontFamily: fonts.displayBold, fontSize: 48, lineHeight: 54, color: colors.ink }}>{passport.data.sim_crs ?? "—"}</Text>
            {wallet.data && (
              <View style={{ flexDirection: "row", gap: space(2), paddingBottom: space(1) }}>
                <Stat icon="logo-bitcoin" value={wallet.data.coins} label={t("wallet.coins")} />
                <Stat icon="star" value={wallet.data.stars_total} label={t("wallet.stars")} />
              </View>
            )}
          </View>
          <Caption>{t("passport.disclaimer")}</Caption>
        </Card>
      )}
      {passport.data && passport.data.bands.length === 0 && (
        <Card tone="accent">
          <Body>{t("passport.noData")}</Body>
        </Card>
      )}
      {passport.data &&
        [...new Set(passport.data.bands.map((b) => b.pack))].map((pack) => (
          <View key={pack} style={{ gap: space(1.5) }}>
            <Title>{packOf(pack)?.pack_name ?? pack}</Title>
            {packOf(pack)?.level_scale && <Caption>{t("today.levelsHint", { scale: packOf(pack)!.level_scale })}</Caption>}
            {passport.data!.bands
              .filter((b) => b.pack === pack)
              .map((band) => {
                const target = profile.data?.target_bands[band.pack]?.[band.skill];
                const reach = target ? levelProgress(band.clb_nclc_low, band.clb_nclc_high, target) : 0;
                return (
                  <Card key={`${band.pack}-${band.skill}`}>
                    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: space(1), flexWrap: "wrap" }}>
                      <Text style={type.headline}>{t(`skills.${band.skill}`)}</Text>
                      {target !== undefined && <Chip label={t("today.goalLevel", { level: target })} tone="accent" icon="flag" />}
                    </View>
                    <ProgressBar value={reach} tone={reach >= 1 ? "success" : reach >= 0.8 ? "warning" : "accent"} />
                    <Body>{t("passport.levelEstimate", { range: levelWords(t, band.clb_nclc_low, band.clb_nclc_high) })}</Body>
                    <Caption>{t("passport.scoreEstimate", { mean: band.mean, low: band.low80, high: band.high80 })}</Caption>
                  </Card>
                );
              })}
          </View>
        ))}
      <Section>
        <ListRow icon="flag" title={t("settings.goal")} onPress={() => router.push("/goal")} />
        <ListRow icon="mic" title={t("studio.title")} onPress={() => router.push("/studio")} />
      </Section>
    </Screen>
  );
}

function Stat({ icon, value, label }: { icon: "logo-bitcoin" | "star"; value: number; label: string }) {
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
