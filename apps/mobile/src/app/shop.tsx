/** The shop: what the coins from missions, lessons and streaks buy (decision 0023). Every item is a treat for the
 * story or a safety net for the streak; nothing here skips learning or changes a score. */
import Ionicons from "@expo/vector-icons/Ionicons";
import * as Haptics from "expo-haptics";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { StyleSheet, Text, View } from "react-native";

import type { CityEntry, Friend, ShopItem, Wallet } from "@/api/types";
import { useApi } from "@/state/auth";
import { useCities } from "@/state/cities";
import { useResource } from "@/state/resource";
import {
  Avatar,
  Button,
  Card,
  ErrorText,
  IconBubble,
  type IconName,
  ListRow,
  Loading,
  Screen,
  Section,
  Segmented,
} from "@/ui/kit";
import { colors, radius, space, type } from "@/ui/theme";

const ICONS: Record<string, IconName> = {
  streak_freeze: "snow",
  cafe_visit: "cafe",
  npc_gift: "gift",
  flat_upgrade: "home",
};

export default function Shop() {
  const { t } = useTranslation();
  const api = useApi();
  const cities = useCities();
  const [chosen, setChosen] = useState<CityEntry["city"] | null>(null);
  const city = chosen ?? cities.data?.[0]?.city ?? null;
  const wallet = useResource(() => api.get<Wallet>("/v1/wallet"), [api]);
  const friends = useResource(
    () =>
      city
        ? api.get<Friend[]>(`/v1/shop/friends?city=${city}`)
        : Promise.resolve(null),
    [api, city],
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bought, setBought] = useState<string | null>(null);
  const [giving, setGiving] = useState(false);

  if (!wallet.data) {
    return (
      <Screen back title={t("shop.title")}>
        {wallet.error ? (
          <ErrorText message={wallet.error} onRetry={wallet.reload} />
        ) : (
          <Loading />
        )}
      </Screen>
    );
  }
  const coins = wallet.data.coins;

  const buy = async (item: string, body: Record<string, string> = {}) => {
    setBusy(item);
    setError(null);
    setBought(null);
    try {
      await api.post<Wallet>(`/v1/shop/${item}`, body);
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setBought(item);
      setGiving(false);
      wallet.reload();
      friends.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const full = (item: ShopItem) =>
    item.limit !== null && item.held >= item.limit;
  const action = (item: ShopItem) => {
    if (item.key === "npc_gift") return () => setGiving((g) => !g);
    const body: Record<string, string> =
      item.key === "cafe_visit" && city ? { city } : {};
    return () => void buy(item.key, body);
  };

  return (
    <Screen back title={t("shop.title")} onRefresh={wallet.reload}>
      <Card tone="accent">
        <View style={styles.balance}>
          <Ionicons name="cash" size={28} color={colors.sunset} />
          <View style={{ flex: 1 }}>
            <Text style={type.title}>
              {t("wallet.coinsCount", { count: coins })}
            </Text>
            <Text style={type.caption}>{t("shop.earn")}</Text>
          </View>
        </View>
      </Card>
      {(cities.data?.length ?? 0) > 1 && city && (
        <Segmented
          options={(cities.data ?? []).map((c) => ({
            value: c.city,
            label: c.name,
          }))}
          value={city}
          onChange={setChosen}
        />
      )}
      {bought && (
        <View style={styles.done} accessibilityLiveRegion="polite">
          <Ionicons name="checkmark-circle" size={18} color={colors.success} />
          <Text style={[type.callout, { flex: 1, color: colors.ink }]}>
            {t(`shop.done.${bought}`)}
          </Text>
        </View>
      )}
      <ErrorText message={error} />
      {wallet.data.items.map((item) => (
        <Card key={item.key}>
          <View style={styles.item}>
            <IconBubble
              name={ICONS[item.key] ?? "pricetag"}
              tone="accent"
              size={44}
            />
            <View style={{ flex: 1, gap: space(0.5) }}>
              <Text style={type.headline}>
                {t(`shop.items.${item.key}.name`)}
              </Text>
              <Text style={type.callout}>
                {t(`shop.items.${item.key}.what`)}
              </Text>
              {item.limit !== null && (
                <Text style={type.caption}>
                  {t(`shop.items.${item.key}.held`, {
                    count: item.held,
                    limit: item.limit,
                  })}
                </Text>
              )}
            </View>
          </View>
          <Button
            label={
              full(item)
                ? t("shop.full")
                : coins < item.price
                  ? t("shop.short", { count: item.price - coins })
                  : t("shop.buy", { price: item.price })
            }
            icon={full(item) ? "checkmark" : "cash"}
            kind={item.key === "npc_gift" && giving ? "tinted" : "primary"}
            busy={busy === item.key}
            disabled={full(item) || coins < item.price || busy !== null}
            onPress={action(item)}
          />
          {item.key === "npc_gift" && giving && (
            <View style={{ gap: space(1) }}>
              {friends.data && friends.data.length === 0 && (
                <Text style={type.caption}>{t("shop.noFriends")}</Text>
              )}
              {friends.data && friends.data.length > 0 && (
                <Section title={t("shop.giveTo")}>
                  {friends.data.map((f) => (
                    <ListRow
                      key={f.npc_key}
                      title={f.name}
                      subtitle={f.gifted_today ? t("shop.giftedToday") : f.role}
                      leading={<Avatar name={f.name} size={36} />}
                      disabled={f.gifted_today || busy !== null}
                      onPress={
                        city
                          ? () =>
                              void buy("npc_gift", { city, npc_key: f.npc_key })
                          : undefined
                      }
                    />
                  ))}
                </Section>
              )}
              {!friends.data && !friends.error && <Loading inline />}
            </View>
          )}
        </Card>
      ))}
      <Text style={[type.caption, { textAlign: "center" }]}>
        {t("shop.fair")}
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  balance: { flexDirection: "row", alignItems: "center", gap: space(1.5) },
  item: {
    flexDirection: "row",
    gap: space(1.5),
    alignItems: "flex-start",
    marginBottom: space(1.5),
  },
  done: {
    flexDirection: "row",
    alignItems: "center",
    gap: space(1),
    padding: space(1.5),
    borderRadius: radius.md,
    backgroundColor: colors.successSoft,
  },
});
