import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Quest } from "@/api/types";
import { useApi } from "@/state/auth";
import { cacheQueue, cachedQueue, queueAnswer, sync } from "@/state/offline";
import { Body, Button, Card, Screen, Title } from "@/ui/kit";

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
    <Screen>
      <Title>{t("phone.title")}</Title>
      {offline && <Body muted>{t("phone.offline")}</Body>}
      {quests.length === 0 && <Body muted>{t("phone.empty")}</Body>}
      {quests.map((quest) => (
        <Card key={quest.id}>
          {quest.text && <Body>{quest.text}</Body>}
          <Body>{quest.prompt}</Body>
          {feedback[quest.id] ? (
            <Body muted>{feedback[quest.id]}</Body>
          ) : (
            quest.options.map((option, i) => <Button key={option} label={option} kind="secondary" onPress={() => void answer(quest, i)} />)
          )}
        </Card>
      ))}
    </Screen>
  );
}
