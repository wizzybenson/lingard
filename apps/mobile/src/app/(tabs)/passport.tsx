import { router } from "expo-router";
import { useTranslation } from "react-i18next";

import type { Passport, Wallet } from "@/api/types";
import { useApi } from "@/state/auth";
import { useResource } from "@/state/resource";
import { Body, Button, Card, ErrorText, Loading, Screen, Title } from "@/ui/kit";

const SCALE: Record<string, string> = { ielts_gt: "IELTS", tef_canada: "TEF" };
const LEVEL: Record<string, string> = { ielts_gt: "CLB", tef_canada: "NCLC" };

/** Conversion tables start at level 4; anything lower is shown as "<4". */
function levelLabel(level: number | null | undefined): string {
  if (level === null || level === undefined) return "–";
  return level < 4 ? "<4" : String(level);
}

export default function PassportScreen() {
  const { t } = useTranslation();
  const api = useApi();
  const passport = useResource(() => api.get<Passport>("/v1/passport"));
  const wallet = useResource(() => api.get<Wallet>("/v1/wallet"));
  return (
    <Screen>
      <Title>{t("passport.title")}</Title>
      {passport.loading && <Loading />}
      <ErrorText message={passport.error} />
      {passport.data && (
        <>
          <Card>
            <Body muted>{t("passport.simCrs")}</Body>
            <Title>{passport.data.sim_crs ?? "—"}</Title>
            <Body muted>{t("passport.disclaimer")}</Body>
          </Card>
          {passport.data.bands.length === 0 && <Body muted>{t("passport.noData")}</Body>}
          {passport.data.bands.map((band) => (
            <Card key={`${band.pack}-${band.skill}`}>
              <Body muted>
                {SCALE[band.pack]} · {band.skill}
              </Body>
              <Title>
                {t("passport.predicted")} {band.mean}
              </Title>
              <Body>{t("passport.range", { low: band.low80, high: band.high80 })}</Body>
              <Body muted>
                {LEVEL[band.pack]} {levelLabel(band.clb_nclc_low)}–{levelLabel(band.clb_nclc_high)}
              </Body>
            </Card>
          ))}
        </>
      )}
      {wallet.data && (
        <Card>
          <Title>{t("wallet.title")}</Title>
          <Body>
            {t("wallet.coins")}: {wallet.data.coins} · {t("wallet.stars")}: {wallet.data.stars_total}
          </Body>
        </Card>
      )}
      <Button label={t("studio.title")} kind="secondary" onPress={() => router.push("/studio")} />
    </Screen>
  );
}
