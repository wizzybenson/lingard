import { useState } from "react";
import { useTranslation } from "react-i18next";

import { wordCount } from "@/games/exam";
import { useApi } from "@/state/auth";
import { useResource } from "@/state/resource";
import { Body, Button, Card, ErrorText, Field, Screen, Title } from "@/ui/kit";

interface Submission {
  id: string;
  pack: string;
  task_type: string;
  word_count: number;
  scores: { band_or_points?: number; dimensions?: { dimension: string; score: number }[] };
  rewrite: string | null;
}

const TASKS = [
  { pack: "ielts_gt", task_id: "task1_letter", min: 150, prompt: "Write a letter to your landlord about a repair that has not been done." },
  { pack: "ielts_gt", task_id: "task2_essay", min: 250, prompt: "Some people think cities should ban cars from their centres. Discuss both views and give your opinion." },
  { pack: "tef_canada", task_id: "section_a", min: 80, prompt: "Écrivez la suite de cet article : « Hier matin, une fuite d'eau a inondé la bibliothèque du quartier… »" },
  { pack: "tef_canada", task_id: "section_b", min: 200, prompt: "« Le télétravail devrait devenir la norme. » Donnez votre point de vue et justifiez-le." },
] as const;

export default function Desk() {
  const { t } = useTranslation();
  const api = useApi();
  const [task, setTask] = useState<(typeof TASKS)[number]>(TASKS[0]);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const history = useResource(() => api.get<Submission[]>("/v1/writing"));

  const submit = async () => {
    try {
      await api.post("/v1/writing", { pack: task.pack, task_id: task.task_id, prompt: task.prompt, text });
      setText("");
      history.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <Screen>
      <Title>Desk</Title>
      {TASKS.map((option) => (
        <Button key={option.task_id} label={`${option.pack} · ${option.task_id}`} kind={option === task ? "primary" : "secondary"} onPress={() => setTask(option)} />
      ))}
      <Card>
        <Body>{task.prompt}</Body>
        <Field label="›" value={text} onChangeText={setText} multiline style={{ minHeight: 220, textAlignVertical: "top" }} />
        <Body muted>{t("exam.words", { count: wordCount(text), min: task.min })}</Body>
        <ErrorText message={error} />
        <Button label={t("exam.submit")} disabled={!text.trim()} onPress={() => void submit()} />
      </Card>
      {history.data?.map((s) => (
        <Card key={s.id}>
          <Body muted>
            {s.pack} · {s.task_type} · {s.word_count}
          </Body>
          {s.scores.band_or_points !== undefined && <Title>{s.scores.band_or_points}</Title>}
          {s.scores.dimensions?.map((d) => (
            <Body key={d.dimension}>
              {d.dimension}: {d.score}
            </Body>
          ))}
          {s.rewrite && <Body muted>{s.rewrite}</Body>}
        </Card>
      ))}
    </Screen>
  );
}
