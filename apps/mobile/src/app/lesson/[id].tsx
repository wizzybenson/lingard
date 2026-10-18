import { useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { ApiClient } from "@/api/client";
import type { LessonRow } from "@/api/types";
import type { Game } from "@/contracts/generated";
import { choices, isCorrect, score, type GameResult } from "@/games/engine";
import { PlayButton } from "@/live/PlayButton";
import { useApi } from "@/state/auth";
import { useResource } from "@/state/resource";
import { Body, Button, Card, ErrorText, Field, Loading, Screen, Title } from "@/ui/kit";

function GameView({
  api,
  lessonId,
  index,
  game,
  onScored,
}: {
  api: ApiClient;
  lessonId: string;
  index: number;
  game: Game;
  onScored: (result: GameResult) => void;
}) {
  const { t } = useTranslation();
  const [answers, setAnswers] = useState<string[]>(game.items.map(() => ""));
  const [result, setResult] = useState<GameResult | null>(null);
  const set = (i: number, value: string) => setAnswers((a) => a.map((v, j) => (j === i ? value : v)));
  return (
    <Card>
      <Title>{t(`games.${game.kind}`)}</Title>
      {game.items.map((item, i) => (
        <Card key={`${item.prompt}-${i}`}>
          {game.kind === "dictation" ? (
            <PlayButton api={api} path={`/v1/lessons/${lessonId}/audio?game=${index}&item=${i}`} label="🔊" />
          ) : (
            <Body>{item.prompt}</Body>
          )}
          {game.kind === "spot_the_error" ? (
            choices(item).map((c) => (
              <Button key={c} label={c} kind={answers[i] === c ? "primary" : "secondary"} disabled={!!result} onPress={() => set(i, c)} />
            ))
          ) : (
            <Field label="›" value={answers[i] ?? ""} editable={!result} onChangeText={(v) => set(i, v)} />
          )}
          {result && <Body muted>{isCorrect(item, answers[i] ?? "") ? "✓" : `✗ → ${item.answer}`}</Body>}
        </Card>
      ))}
      {result ? (
        <Body>{t("games.score", { score: result.correct, total: result.total })}</Body>
      ) : (
        <Button
          label={t("games.check")}
          onPress={() => {
            const scored = score(game, answers);
            setResult(scored);
            onScored(scored);
          }}
        />
      )}
    </Card>
  );
}

export default function LessonScreen() {
  const { t } = useTranslation();
  const api = useApi();
  const { id } = useLocalSearchParams<{ id: string }>();
  const lesson = useResource(() => api.get<LessonRow>(`/v1/lessons/${id}`), [id]);
  const [results, setResults] = useState<Record<number, GameResult>>({});
  const [finished, setFinished] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!lesson.data) return <Screen back><Loading /></Screen>;
  const content = lesson.data.content;
  const scored = Object.values(results);
  const correct = scored.reduce((n, r) => n + r.correct, 0);
  const total = scored.reduce((n, r) => n + r.total, 0);
  const finish = async () => {
    try {
      await api.post(`/v1/lessons/${id}/complete`, { correct, total: Math.max(total, 1) });
      setFinished(t("school.finished", { score: correct, total }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  return (
    <Screen back>
      <Title>{content.title}</Title>
      <Card>
        <Body muted>{t("school.rule")}</Body>
        <Body>{content.rule}</Body>
      </Card>
      <Card>
        <Body muted>{t("school.yourExamples")}</Body>
        {content.examples.map((e) => (
          <Body key={e.learner_said}>
            ✗ {e.learner_said}
            {"\n"}✓ {e.better}
          </Body>
        ))}
      </Card>
      {content.games.map((game, i) => (
        <GameView key={`${game.kind}-${i}`} api={api} lessonId={id} index={i} game={game} onScored={(r) => setResults((all) => ({ ...all, [i]: r }))} />
      ))}
      <Card>
        <Body>{t("school.homework")}</Body>
        <Body muted>{content.homework.story_beat}</Body>
      </Card>
      <ErrorText message={error} />
      {finished ? (
        <Body>{finished}</Body>
      ) : lesson.data.status === "done" ? (
        <Body muted>{t("school.done")}</Body>
      ) : (
        <Button label={t("school.finish")} disabled={scored.length < content.games.length} onPress={() => void finish()} />
      )}
    </Screen>
  );
}
