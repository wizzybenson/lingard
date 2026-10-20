import { answeredQuests, cacheQueue, cachedQueue, pendingAnswers, queueAnswer, rememberAnswer, sync } from "@/state/offline";

jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock"),
);

test("queue cached offline and answers synced later, keeping failures", async () => {
  await cacheQueue([{ id: "q1", kind: "read", language: "fr", prompt: "?", options: ["a"], text: null, node_key: null }]);
  expect((await cachedQueue())[0]?.id).toBe("q1");
  await queueAnswer({ quest_id: "q1", answer: 0, language: "fr", synced_at: "2026-10-14T08:00:00Z" });
  await queueAnswer({ quest_id: "q2", answer: 1, language: "fr", synced_at: "2026-10-14T08:01:00Z" });
  const synced = await sync(async (a) => {
    if (a.quest_id === "q2") throw new Error("offline");
  });
  expect(synced).toBe(1);
  expect((await pendingAnswers()).map((a) => a.quest_id)).toEqual(["q2"]);
});

test("answers are remembered for the current queue only", async () => {
  const quest = (id: string) => ({ id, kind: "read" as const, language: "fr" as const, prompt: "?", options: ["a", "b"], text: null, node_key: null });
  await rememberAnswer("old", { choice: 0, correct: true, answer: 0 }, [quest("old")]);
  await rememberAnswer("new", { choice: 1, correct: false, answer: 0 }, [quest("new")]);
  expect(await answeredQuests()).toEqual({ new: { choice: 1, correct: false, answer: 0 } });
});
