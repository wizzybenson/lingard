import { reachable } from "@/config";

test("a phone in development reaches the computer's API and LiveKit instead of itself", () => {
  expect(reachable("http://localhost:58000", "192.168.1.20:8081", "ios")).toBe("http://192.168.1.20:58000");
  expect(reachable("ws://localhost:57880", "192.168.1.20:8081", "ios")).toBe("ws://192.168.1.20:57880");
  expect(reachable("http://127.0.0.1:58000/v1", "10.0.0.5:8081", "android")).toBe("http://10.0.0.5:58000/v1");
});

test("real hosts, the web and missing dev hosts are left alone", () => {
  expect(reachable("https://api.lingard.app", "192.168.1.20:8081", "ios")).toBe("https://api.lingard.app");
  expect(reachable("http://localhost:58000", "192.168.1.20:8081", "web")).toBe("http://localhost:58000");
  expect(reachable("http://localhost:58000", null, "ios")).toBe("http://localhost:58000");
  expect(reachable("http://localhost:58000", "localhost:8081", "ios")).toBe("http://localhost:58000");
});
