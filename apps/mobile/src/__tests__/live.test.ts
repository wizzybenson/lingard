import { act, renderHook } from "@testing-library/react-native";
import { Platform } from "react-native";

// The room logic is the same everywhere; the web path avoids the native audio session's dynamic import.
// The hook reads the platform when it loads, so it is required after the override.
Object.defineProperty(Platform, "OS", { get: () => "web" });
const { useLiveScene } = require("@/live/useLiveScene") as typeof import("@/live/useLiveScene");

const mockRooms: { connect: jest.Mock; disconnect: jest.Mock }[] = [];
let mockJoin: () => Promise<void> = () => Promise.resolve();

jest.mock("expo-haptics", () => ({ selectionAsync: jest.fn(), impactAsync: jest.fn(), ImpactFeedbackStyle: {} }));
jest.mock("expo-constants", () => ({ expoConfig: {} }));
jest.mock("@livekit/react-native", () => ({ AudioSession: { startAudioSession: jest.fn(), stopAudioSession: jest.fn() } }));
jest.mock("livekit-client", () => ({
  DisconnectReason: { DUPLICATE_IDENTITY: 2 },
  RoomEvent: {},
  Track: { Kind: { Audio: "audio" } },
  Room: jest.fn().mockImplementation(() => {
    const room = {
      on: jest.fn(),
      connect: jest.fn(() => mockJoin()),
      disconnect: jest.fn(() => Promise.resolve()),
      localParticipant: { identity: "me", setMicrophoneEnabled: jest.fn(() => Promise.resolve()) },
    };
    mockRooms.push(room);
    return room;
  }),
}));

const ticket = { livekit_url: "ws://localhost:57880", token: "t" } as never;

beforeEach(() => {
  mockRooms.length = 0;
  mockJoin = () => Promise.resolve();
});

test("a double tap joins one room, not two that evict each other", async () => {
  const { result, unmount } = await renderHook(() => useLiveScene());
  const fetch = jest.fn(() => Promise.resolve(ticket));
  await act(async () => {
    await Promise.all([result.current.connect(fetch), result.current.connect(fetch)]);
  });
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(mockRooms).toHaveLength(1);
  expect(result.current.status).toBe("live");
  await unmount();
});

test("leaving the screen mid-join still disconnects the room", async () => {
  jest.useFakeTimers();
  mockJoin = () => new Promise(() => undefined); // never finishes
  const { result, unmount } = await renderHook(() => useLiveScene());
  await act(async () => {
    void result.current.connect(() => Promise.resolve(ticket));
    await Promise.resolve();
  });
  expect(mockRooms).toHaveLength(1);
  await unmount();
  expect(mockRooms[0]!.disconnect).toHaveBeenCalled();
  jest.runOnlyPendingTimers();
  jest.useRealTimers();
});

test("a join that hangs gives up with a timeout the learner can retry", async () => {
  jest.useFakeTimers();
  mockJoin = () => new Promise(() => undefined);
  const { result, unmount } = await renderHook(() => useLiveScene());
  await act(async () => {
    const pending = result.current.connect(() => Promise.resolve(ticket));
    await jest.advanceTimersByTimeAsync(21_000);
    await pending;
  });
  expect(result.current.status).toBe("error");
  expect(result.current.error).toEqual({ code: "timeout" });
  expect(mockRooms[0]!.disconnect).toHaveBeenCalled();
  await unmount();
  jest.useRealTimers();
});
