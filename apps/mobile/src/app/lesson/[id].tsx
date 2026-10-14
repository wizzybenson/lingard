import { useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { LessonRow } from "@/api/types";
import type { Game } from "@/contracts/generated";
import { choices, score, type GameResult } from "@/games/engine";
import { useApi } from "@/state/auth";
import { useResource } from "@/state/resource";
import { Body, Button, Card, Field, Loading, Screen, Title } from "@/ui/kit";

function GameView({ game }: { game: Game }) {
  const { t } = useTranslation();
  const [answers, setAnswers] = useState<string[]>(game.items.map(() => ""));
  const [result, setResult] = useState<GameResult | null>(null);
  const multipleChoice = game.kind === "spot_the_error" || game.kind === "sentence_race";
  return (
    <Card>
      <Title>{t(`games.${game.kind}`)}</Title>
      {game.items.map((item, i) => (
        <Card key={`${item.prompt}-${i}`}>
          <Body>{game.kind === "dictation" ? "🔊" : item.prompt}</Body>
          {multipleChoice && game.kind === "spot_the_error" ? (
            choices(item).map((c) => (
              <Button key={c} label={c} kind={answers[i] === c ? "primary" : "secondary"} onPress={() => setAnswers((a) => a.map((v, j) => (j === i ? c : v)))} />
            ))
          ) : (
            <Field label="›" value={answers[i] ?? ""} onChangeText={(v) => setAnswers((a) => a.map((x, j) => (j === i ? v : x)))} />
          )}
        </Card>
      ))}
      {result ? (
        <Body>{t("games.score", { score: result.correct, total: result.total })}</Body>
      ) : (
        <Button label={t("games.check")} onPress={() => setResult(score(game, answers))} />
      )}
    </Card>
  );
}

export default function LessonScreen() {
  const { t } = useTranslation();
  const api = useApi();
  const { id } = useLocalSearchParams<{ id: string }>();
  const lesson = useResource(() => api.get<LessonRow>(`/v1/lessons/${id}`), [id]);
  if (!lesson.data) return <Screen><Loading /></Screen>;
  const content = lesson.data.content;
  return (
    <Screen>
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
        <GameView key={`${game.kind}-${i}`} game={game} />
      ))}
      <Card>
        <Body>{t("school.homework")}</Body>
        <Body muted>{content.homework.story_beat}</Body>
      </Card>
    </Screen>
  );
}
