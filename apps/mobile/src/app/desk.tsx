/** Writing desk: exam writing tasks with practice prompts from content, scored by the examiner in the background.
 * The draft is kept on the device per task and topic, so leaving the screen never loses a text. */
import AsyncStorage from "@react-native-async-storage/async-storage";
import Ionicons from "@expo/vector-icons/Ionicons";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import type { WritingTask } from "@/api/types";
import { wordCount } from "@/games/exam";
import { useApi } from "@/state/auth";
import { useResource } from "@/state/resource";
import { Body, Button, Card, Chip, ErrorText, Field, Loading, Overline, ProgressBar, Screen, Segmented, Title } from "@/ui/kit";
import { colors, radius, space, type } from "@/ui/theme";

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
/** Criterion scores are on the pack's own scale: IELTS bands (9) or NCLC levels (12). */
const CRITERION_MAX: Record<string, number> = { ielts_gt: 9, tef_canada: 12 };
const draftKey = (task: string, prompt: number) => `lingard.desk.${task}.${prompt}`;

export default function Desk() {
  const { t } = useTranslation();
  const api = useApi();
  const tasks = useResource(() => api.get<WritingTask[]>("/v1/writing/tasks"), [api]);
  const history = useResource(() => api.get<Submission[]>("/v1/writing"), [api]);
  const [pack, setPack] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [promptIndex, setPromptIndex] = useState(0);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [scoring, setScoring] = useState(false);
  const waitingSince = useRef(0);
  const knownCount = useRef(0);

  const all = tasks.data ?? [];
  const packs = [...new Map(all.map((x) => [x.pack, x.pack_name])).entries()];
  const currentPack = pack ?? packs[0]?.[0] ?? null;
  const packTasks = all.filter((x) => x.pack === currentPack);
  const task = packTasks.find((x) => x.task_id === taskId) ?? packTasks[0];
  const key = task ? draftKey(`${task.pack}.${task.task_id}`, promptIndex) : null;

  // Restore the draft for this task and topic; the editor follows the key, never the other way round.
  useEffect(() => {
    if (!key) return;
    let live = true;
    AsyncStorage.getItem(key)
      .then((saved) => live && setText(saved ?? ""))
      .catch(() => live && setText(""));
    return () => {
      live = false;
    };
  }, [key]);

  const edit = (value: string) => {
    setText(value);
    if (key) void AsyncStorage.setItem(key, value).catch(() => undefined);
  };

  useEffect(() => {
    if (!scoring) return;
    const timer = setInterval(() => {
      void api.get<Submission[]>("/v1/writing").then((rows) => {
        if (rows.length > knownCount.current) {
          setScoring(false);
          history.reload();
        } else if (Date.now() - waitingSince.current > SCORING_TIMEOUT_MS) {
          setScoring(false);
          setError(t("writing.scoringTimeout"));
        }
      });
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [api, scoring, history, t]);

  if (!tasks.data) return <Screen back>{tasks.error ? <ErrorText message={tasks.error} onRetry={tasks.reload} /> : <Loading />}</Screen>;
  if (!task) return <Screen back><Body muted>{t("phone.empty")}</Body></Screen>;
  const prompt = task.prompts[promptIndex % Math.max(task.prompts.length, 1)] ?? "";
  const words = wordCount(text);
  const enough = words >= task.min_words;

  const submit = async () => {
    setError(null);
    try {
      knownCount.current = history.data?.length ?? 0;
      await api.post("/v1/writing", { pack: task.pack, task_id: task.task_id, prompt, text });
      // eslint-disable-next-line react-hooks/purity -- runs in the submit handler after the await, not during render
      waitingSince.current = Date.now();
      setScoring(true);
      edit("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const footer = scoring ? (
    <View style={styles.scoring}>
      <ActivityIndicator color={colors.accent} />
      <Text style={[type.callout, { flex: 1 }]}>{t("writing.scoring")}</Text>
    </View>
  ) : (
    <View style={styles.footerRow}>
      <Chip label={t("writing.wordCount", { count: words, min: task.min_words })} tone={enough ? "success" : "plain"} icon={enough ? "checkmark-circle" : "text"} />
      <View style={{ flex: 1 }}>
        <Button label={t("writing.submit")} icon="send" disabled={!text.trim()} onPress={() => void submit()} />
      </View>
    </View>
  );

  return (
    <Screen back title={t("writing.title")} footer={footer}>
      {packs.length > 1 && (
        <Segmented
          options={packs.map(([value, label]) => ({ value, label }))}
          value={currentPack}
          onChange={(value) => {
            setPack(value);
            setTaskId(null);
            setPromptIndex(0);
          }}
        />
      )}
      <Segmented
        options={packTasks.map((x) => ({ value: x.task_id, label: t(`writing.kinds.${x.kind}`, { defaultValue: x.task_id }) }))}
        value={task.task_id}
        onChange={(value) => {
          setTaskId(value);
          setPromptIndex(0);
        }}
      />
      <Card style={{ gap: space(1.5) }}>
        <View style={styles.row}>
          <Overline>{t("writing.topic")}</Overline>
          <View style={{ flex: 1 }} />
          <Chip label={t("writing.minWords", { count: task.min_words })} icon="text" />
          <Chip label={t("writing.aboutMinutes", { count: task.suggested_minutes })} icon="time-outline" />
        </View>
        <Text style={[type.body, { fontSize: 17, lineHeight: 26 }]}>{prompt}</Text>
        {task.prompts.length > 1 && (
          <Button label={t("writing.another")} kind="ghost" icon="refresh" onPress={() => setPromptIndex((n) => n + 1)} />
        )}
      </Card>
      <Field label={t("writing.yourText")} value={text} onChangeText={edit} multiline style={{ minHeight: 280, textAlignVertical: "top", paddingTop: space(1.5), lineHeight: 24 }} />
      <Text style={type.caption}>
        <Ionicons name="phone-portrait-outline" size={12} color={colors.muted} /> {t("writing.draftSaved")}
      </Text>
      <ErrorText message={error} />

      {history.data && history.data.length > 0 && <Title>{t("writing.history")}</Title>}
      {history.data?.map((s) => (
        <Card key={s.id} style={{ gap: space(1.5) }}>
          <View style={styles.row}>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={type.headline}>{t(`writing.kinds.${s.task_type}`, { defaultValue: s.task_type })}</Text>
              <Text style={type.caption}>
                {all.find((x) => x.pack === s.pack)?.pack_name ?? s.pack} · {t("writing.words", { count: s.word_count })}
              </Text>
            </View>
            {s.scores.band_or_points !== undefined && (
              <View style={styles.score}>
                <Text style={type.caption}>{t("writing.score")}</Text>
                <Text style={[type.title, { color: colors.accentDeep }]}>{s.scores.band_or_points}</Text>
              </View>
            )}
          </View>
          {s.scores.dimensions?.map((d) => (
            <View key={d.dimension} style={{ gap: 6 }}>
              <View style={styles.row}>
                <Text style={[type.callout, { flex: 1 }]}>{t(`rubric.${d.dimension}`, { defaultValue: d.dimension })}</Text>
                <Text style={type.headline}>{d.score}</Text>
              </View>
              <ProgressBar value={d.score / (CRITERION_MAX[s.pack] ?? 9)} />
              {d.rationale ? <Text style={type.caption}>{d.rationale}</Text> : null}
            </View>
          ))}
          {s.rewrite && (
            <View style={styles.rewrite}>
              <Overline>{t("writing.stronger")}</Overline>
              <Text style={type.body}>{s.rewrite}</Text>
            </View>
          )}
        </Card>
      ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: space(1) },
  footerRow: { flexDirection: "row", alignItems: "center", gap: space(1.5) },
  scoring: { flexDirection: "row", alignItems: "center", gap: space(1.5), minHeight: 54 },
  score: { alignItems: "center", backgroundColor: colors.accentSoft, borderRadius: radius.md, paddingHorizontal: space(1.5), paddingVertical: space(0.75) },
  rewrite: { backgroundColor: colors.paper, borderRadius: radius.md, padding: space(1.5), gap: space(1) },
});
