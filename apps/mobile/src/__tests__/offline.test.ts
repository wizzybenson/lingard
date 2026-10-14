import { cacheQueue, cachedQueue, pendingAnswers, queueAnswer, sync } from "@/state/offline";

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
