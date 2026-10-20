/** Glance mode as a phone inbox: one message at a time, an answer checked at once, then the next (SPEC §19.3).
 * The cached queue paints first; the network refreshes it behind. */
import * as Haptics from "expo-haptics";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { StyleSheet, Text, View } from "react-native";
import Animated, { FadeIn, FadeInDown } from "react-native-reanimated";

import type { Quest } from "@/api/types";
import { useApi } from "@/state/auth";
import { answeredQuests, cacheQueue, cachedQueue, queueAnswer, rememberAnswer, sync, type Answered } from "@/state/offline";
import { Body, Button, Card, Chip, Choice, IconBubble, Loading, ProgressBar, Screen, Title, type ChoiceState } from "@/ui/kit";
import { colors, radius, space, type } from "@/ui/theme";

function choiceState(index: number, picked: Answered | undefined): ChoiceState {
  if (!picked) return "idle";
  if (picked.answer === null) return index === picked.choice ? "picked" : "dim";
  if (index === picked.answer) return "right";
  return index === picked.choice ? "wrong" : "dim";
}

export default function Phone() {
  const { t } = useTranslation();
  const api = useApi();
  const [quests, setQuests] = useState<Quest[] | null>(null);
  const [answered, setAnswered] = useState<Record<string, Answered>>({});
  const [checking, setChecking] = useState<Record<string, number>>({});
  const [viewing, setViewing] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);

  const refresh = useCallback(async () => {
    try {
      await sync((a) => api.post(`/v1/glance/answer?language=${a.language}`, a).then(() => undefined));
      const fresh = await api.get<Quest[]>("/v1/glance");
      await cacheQueue(fresh);
      setQuests(fresh);
      setOffline(false);
    } catch {
      setQuests((q) => q ?? []);
      setOffline(true);
    }
  }, [api]);

  useEffect(() => {
    void (async () => {
      const [cached, done] = await Promise.all([cachedQueue(), answeredQuests()]);
      setAnswered(done);
      if (cached.length) setQuests((q) => q ?? cached);
      await refresh();
    })();
  }, [refresh]);

  const answer = async (quest: Quest, index: number) => {
    setChecking((c) => ({ ...c, [quest.id]: index }));
    void Haptics.selectionAsync();
    const pending = { quest_id: quest.id, answer: index, language: quest.language, synced_at: new Date().toISOString() };
    let result: Answered;
    try {
      const reply = await api.post<{ correct: boolean; answer: number }>(`/v1/glance/answer?language=${quest.language}`, pending);
      result = { choice: index, correct: reply.correct, answer: reply.answer };
      void Haptics.notificationAsync(reply.correct ? Haptics.NotificationFeedbackType.Success : Haptics.NotificationFeedbackType.Error);
    } catch {
      await queueAnswer(pending);
      setOffline(true);
      result = { choice: index, correct: null, answer: null };
    }
    setAnswered((a) => ({ ...a, [quest.id]: result }));
    setViewing(quest.id);
    await rememberAnswer(quest.id, result, quests ?? []);
  };

  const list = quests ?? [];
  const unanswered = list.filter((q) => !answered[q.id]);
  const shown = list.find((q) => q.id === viewing) ?? unanswered[0] ?? null;
  const doneCount = list.length - unanswered.length;
  const position = Math.min(list.length, doneCount + (shown && !answered[shown.id] ? 1 : 0));
  const rightCount = list.filter((q) => answered[q.id]?.correct).length;
  const next = () => setViewing(null);
  const verdict = shown ? answered[shown.id] : undefined;
  const checkingIndex = shown ? checking[shown.id] : undefined;
  const shownPick = verdict ?? (checkingIndex === undefined ? undefined : { choice: checkingIndex, correct: null, answer: null });

  return (
    <Screen title={t("phone.title")} onRefresh={refresh} footer={verdict ? <Verdict key={shown?.id} picked={verdict} onNext={next} /> : undefined}>
      <Body muted>{t("phone.intro")}</Body>
      {offline && <Chip label={t("phone.offline")} tone="warning" icon="cloud-offline" />}
      {quests === null && <Loading />}
      {quests !== null && list.length === 0 && (
        <Card style={styles.centred}>
          <IconBubble name="chatbubbles" tone="accent" size={56} />
          <Body muted>{t("phone.empty")}</Body>
        </Card>
      )}
      {list.length > 0 && (
        <View style={styles.progress}>
          <View style={{ flex: 1 }}>
            <ProgressBar value={doneCount / list.length} />
          </View>
          <Text style={type.caption}>{t("phone.progress", { n: position, total: list.length })}</Text>
        </View>
      )}
      {list.length > 0 && !shown && (
        <Animated.View entering={FadeIn.duration(250)}>
          <Card style={styles.centred}>
            <IconBubble name="checkmark-done" tone="success" size={64} />
            <Title>{t("phone.doneTitle")}</Title>
            <Body>{t("phone.doneScore", { right: rightCount, total: list.length })}</Body>
            <Body muted>{t("phone.doneBody")}</Body>
          </Card>
        </Animated.View>
      )}
      {shown && (
        <Animated.View key={shown.id} entering={FadeInDown.duration(260)}>
          <Message quest={shown} picked={shownPick} onAnswer={(i) => void answer(shown, i)} />
        </Animated.View>
      )}
    </Screen>
  );
}

function Message({ quest, picked, onAnswer }: { quest: Quest; picked: Answered | undefined; onAnswer: (index: number) => void }) {
  const { t } = useTranslation();
  return (
    <Card style={{ gap: space(2) }}>
      <View style={styles.sender}>
        <IconBubble name={quest.kind === "read" ? "newspaper" : "sparkles"} tone={quest.kind === "read" ? "accent" : "sunset"} />
        <Text style={[type.headline, { flex: 1 }]}>{t(`phone.from.${quest.kind}`)}</Text>
      </View>
      {quest.text && (
        <View style={styles.bubble}>
          <Text style={type.body}>{quest.text}</Text>
        </View>
      )}
      <Text style={[type.headline, { fontSize: 18, lineHeight: 25 }]}>{quest.prompt}</Text>
      <View style={{ gap: space(1) }}>
        {quest.options.map((option, i) => (
          <Choice key={option} label={option} index={i} state={choiceState(i, picked)} onPress={picked ? undefined : () => onAnswer(i)} />
        ))}
      </View>
    </Card>
  );
}

/** The verdict and the way on, pinned in thumb reach so a long text never pushes them off screen. */
function Verdict({ picked, onNext }: { picked: Answered; onNext: () => void }) {
  const { t } = useTranslation();
  const look =
    picked.correct === null
      ? { tone: "warning" as const, icon: "cloud-offline" as const, text: t("phone.saved") }
      : picked.correct
        ? { tone: "success" as const, icon: "checkmark-circle" as const, text: t("phone.correct") }
        : { tone: "danger" as const, icon: "close-circle" as const, text: `${t("phone.wrong")} ${t("phone.rightIs")}` };
  return (
    <Animated.View entering={FadeInDown.duration(200)} style={{ gap: space(1.25) }}>
      <Chip label={look.text} tone={look.tone} icon={look.icon} />
      <Button label={t("phone.next")} icon="arrow-forward" onPress={onNext} />
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  centred: { alignItems: "center", paddingVertical: space(4), gap: space(1.5) },
  progress: { flexDirection: "row", alignItems: "center", gap: space(1.5) },
  sender: { flexDirection: "row", alignItems: "center", gap: space(1.5) },
  bubble: { backgroundColor: colors.paper, borderRadius: radius.lg, borderTopLeftRadius: radius.sm, padding: space(2) },
});
