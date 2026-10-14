import { useLocalSearchParams } from "expo-router";
import { useTranslation } from "react-i18next";

import type { SessionView } from "@/api/types";
import { useApi } from "@/state/auth";
import { useResource } from "@/state/resource";
import { Body, Card, Loading, Screen, Title } from "@/ui/kit";

const POLL_MS = 3000;

export default function NotebookScreen() {
  const { t } = useTranslation();
  const api = useApi();
  const { id } = useLocalSearchParams<{ id: string }>();
  const session = useResource(async () => {
    for (let i = 0; i < 40; i += 1) {
      const view = await api.get<SessionView>(`/v1/sessions/${id}`);
      if (view.notebook) return view;
      await new Promise((r) => setTimeout(r, POLL_MS));
    }
    return api.get<SessionView>(`/v1/sessions/${id}`);
  }, [id]);
  const notebook = session.data?.notebook;
  if (!notebook) return <Screen><Loading /></Screen>;
  return (
    <Screen>
      <Title>{t("notebook.title")}</Title>
      {notebook.encouragement ? <Body>{notebook.encouragement}</Body> : null}
      <Card>
        <Body muted>{t("notebook.corrections")}</Body>
        {notebook.corrections.map((c) => (
          <Body key={`${c.node_key}-${c.learner_said}`}>
            ✗ {c.learner_said}
            {"\n"}✓ {c.correction}
            {"\n"}
            {c.explanation}
          </Body>
        ))}
      </Card>
      <Card>
        <Body muted>{t("notebook.review")}</Body>
        <Body>{notebook.review_items.length}</Body>
      </Card>
    </Screen>
  );
}
