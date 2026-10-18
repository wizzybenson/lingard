/** Writing desk: exam writing tasks with practice prompts from content, scored by the examiner in the background. */
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { WritingTask } from "@/api/types";
import { wordCount } from "@/games/exam";
import { useApi } from "@/state/auth";
import { useResource } from "@/state/resource";
import { Body, Button, Card, ErrorText, Field, Loading, Screen, Title } from "@/ui/kit";

interface Submission {
  id: string;
  pack: string;
  task_type: string;
  word_count: number;
  scores: { band_or_points?: number; dimensions?: { dimension: string; score: number; rationale?: string }[] };
  rewrite: string | null;
}

const POLL_MS = 4000;
const SCORING_TIMEOUT_MS = 3 * 60 * 1000;

export default function Desk() {
  const { t } = useTranslation();
  const api = useApi();
  const tasks = useResource(() => api.get<WritingTask[]>("/v1/writing/tasks"), [api]);
  const history = useResource(() => api.get<Submission[]>("/v1/writing"), [api]);
  const [choice, setChoice] = useState<{ task: number; prompt: number }>({ task: 0, prompt: 0 });
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [scoring, setScoring] = useState(false);
  const waitingSince = useRef(0);
  const knownCount = useRef(0);

  useEffect(() => {
    if (!scoring) return;
    const timer = setInterval(() => {
      void api.get<Submission[]>("/v1/writing").then((rows) => {
        if (rows.length > knownCount.current) {
          setScoring(false);
          history.reload();
        } else if (Date.now() - waitingSince.current > SCORING_TIMEOUT_MS) {
          setScoring(false);
          setError(t("city.planningTimeout"));
        }
      });
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [api, scoring, history, t]);

  if (!tasks.data) return <Screen back>{tasks.error ? <ErrorText message={tasks.error} /> : <Loading />}</Screen>;
  const task = tasks.data[choice.task];
  if (!task) return <Screen back><Body muted>{t("phone.empty")}</Body></Screen>;
  const prompt = task.prompts[choice.prompt % Math.max(task.prompts.length, 1)] ?? "";
  const label = (option: WritingTask) => `${option.pack_name} · ${t(`writing.kinds.${option.kind}`, { defaultValue: option.task_id })}`;

  const submit = async () => {
    setError(null);
    try {
      knownCount.current = history.data?.length ?? 0;
      await api.post("/v1/writing", { pack: task.pack, task_id: task.task_id, prompt, text });
      waitingSince.current = Date.now();
      setScoring(true);
      setText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <Screen back title={t("writing.title")}>
      {tasks.data.map((option, i) => (
        <Button key={`${option.pack}-${option.task_id}`} label={label(option)} kind={i === choice.task ? "primary" : "secondary"} onPress={() => setChoice({ task: i, prompt: 0 })} />
      ))}
      <Card>
        <Body>{prompt}</Body>
        {task.prompts.length > 1 && (
          <Button label={t("writing.another")} kind="secondary" onPress={() => setChoice((c) => ({ ...c, prompt: c.prompt + 1 }))} />
        )}
        <Field label="›" value={text} onChangeText={setText} multiline style={{ minHeight: 220, textAlignVertical: "top" }} />
        <Body muted>{t("exam.words", { count: wordCount(text), min: task.min_words })}</Body>
        <ErrorText message={error} />
        {scoring ? <Body muted>{t("writing.scoring")}</Body> : <Button label={t("exam.submit")} disabled={!text.trim()} onPress={() => void submit()} />}
      </Card>
      {history.data && history.data.length > 0 && <Title>{t("writing.history")}</Title>}
      {history.data?.map((s) => (
        <Card key={s.id}>
          <Body muted>
            {tasks.data?.find((x) => x.pack === s.pack)?.pack_name ?? s.pack} · {t(`writing.kinds.${s.task_type}`, { defaultValue: s.task_type })} ·{" "}
            {t("writing.words", { count: s.word_count })}
          </Body>
          {s.scores.band_or_points !== undefined && <Title>{s.scores.band_or_points}</Title>}
          {s.scores.dimensions?.map((d) => (
            <Body key={d.dimension}>
              {t(`rubric.${d.dimension}`, { defaultValue: d.dimension })}: {d.score}
              {d.rationale ? ` · ${d.rationale}` : ""}
            </Body>
          ))}
          {s.rewrite && <Body muted>{s.rewrite}</Body>}
        </Card>
      ))}
    </Screen>
  );
}
