import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Quest } from "@/api/types";
import { useApi } from "@/state/auth";
import { cacheQueue, cachedQueue, queueAnswer, sync } from "@/state/offline";
import { Body, Button, Card, Chip, IconBubble, Screen } from "@/ui/kit";

export default function Phone() {
  const { t } = useTranslation();
  const api = useApi();
  const [quests, setQuests] = useState<Quest[]>([]);
  const [offline, setOffline] = useState(false);
  const [feedback, setFeedback] = useState<Record<string, string>>({});

  useEffect(() => {
    void (async () => {
      try {
        await sync((a) => api.post(`/v1/glance/answer?language=${a.language}`, a).then(() => undefined));
        const fresh = await api.get<Quest[]>("/v1/glance");
        await cacheQueue(fresh);
        setQuests(fresh);
        setOffline(false);
      } catch {
        setQuests(await cachedQueue());
        setOffline(true);
      }
    })();
  }, [api]);

  const answer = async (quest: Quest, index: number) => {
    const pending = { quest_id: quest.id, answer: index, language: quest.language, synced_at: new Date().toISOString() };
    try {
      const result = await api.post<{ correct: boolean }>(`/v1/glance/answer?language=${quest.language}`, pending);
      setFeedback((f) => ({ ...f, [quest.id]: result.correct ? t("phone.correct") : t("phone.wrong") }));
    } catch {
      await queueAnswer(pending);
      setOffline(true);
      setFeedback((f) => ({ ...f, [quest.id]: t("phone.offline") }));
    }
  };

  return (
    <Screen title={t("phone.title")}>
      <Body muted>{t("phone.intro")}</Body>
      {offline && <Chip label={t("phone.offline")} tone="warning" icon="cloud-offline" />}
      {quests.length === 0 && (
        <Card style={{ alignItems: "center", paddingVertical: 32 }}>
          <IconBubble name="chatbubbles" tone="accent" size={56} />
          <Body muted>{t("phone.empty")}</Body>
        </Card>
      )}
      {quests.map((quest) => (
        <Card key={quest.id}>
          {quest.text && <Body>{quest.text}</Body>}
          <Body>{quest.prompt}</Body>
          {feedback[quest.id] ? (
            <Chip
              label={feedback[quest.id]!}
              tone={feedback[quest.id] === t("phone.correct") ? "success" : feedback[quest.id] === t("phone.wrong") ? "danger" : "warning"}
              icon={feedback[quest.id] === t("phone.correct") ? "checkmark-circle" : feedback[quest.id] === t("phone.wrong") ? "close-circle" : "cloud-offline"}
            />
          ) : (
            quest.options.map((option, i) => <Button key={option} label={option} kind="secondary" onPress={() => void answer(quest, i)} />)
          )}
        </Card>
      ))}
    </Screen>
  );
}
