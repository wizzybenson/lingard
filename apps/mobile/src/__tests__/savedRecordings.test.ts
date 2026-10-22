// A take is kept on the device until the server has it: a dropped connection never costs the learner a recording.
// (jest.mock calls are hoisted above this import.)
import { keep, saved, sent } from "@/live/savedRecordings";

const mockFiles = new Map<string, boolean>();
const mockStore = new Map<string, string>();

jest.mock("@react-native-async-storage/async-storage", () => ({
  getItem: jest.fn((k: string) => Promise.resolve(mockStore.get(k) ?? null)),
  setItem: jest.fn((k: string, v: string) => Promise.resolve(void mockStore.set(k, v))),
  removeItem: jest.fn((k: string) => Promise.resolve(void mockStore.delete(k))),
}));
jest.mock("expo-file-system", () => {
  class Directory {
    uri: string;
    constructor(...parts: (string | { uri: string })[]) {
      this.uri = parts.map((p) => (typeof p === "string" ? p : p.uri)).join("/");
    }
    get exists() {
      return true;
    }
    create() {}
  }
  class File {
    uri: string;
    constructor(...parts: (string | { uri: string })[]) {
      this.uri = parts.map((p) => (typeof p === "string" ? p : p.uri)).join("/");
    }
    get exists() {
      return mockFiles.get(this.uri) ?? false;
    }
    delete() {
      mockFiles.delete(this.uri);
    }
    copy(to: { uri: string }) {
      mockFiles.set(to.uri, true);
      return Promise.resolve();
    }
  }
  return { Directory, File, Paths: { document: { uri: "doc" } } };
});


test("a take waits on the device until it is sent, and stays playable afterwards", async () => {
  mockFiles.set("tmp/take.m4a", true);
  const kept = await keep("gym:fr:u:rue", "tmp/take.m4a");
  expect(kept).toBe("doc/recordings/gym_fr_u_rue.m4a");
  expect(await saved("gym:fr:u:rue")).toBe(kept); // the upload failed: offered again, even after a restart
  await sent("gym:fr:u:rue");
  expect(await saved("gym:fr:u:rue")).toBeNull(); // the server has it: no longer waiting
  expect(mockFiles.get(kept)).toBe(true); // but still there for "hear yourself"
  mockFiles.set("tmp/next.m4a", true);
  expect(await keep("gym:fr:u:rue", "tmp/next.m4a")).toBe(kept); // the next take replaces it: one file per line
});
