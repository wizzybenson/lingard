/** What a stop of today's path says and where it leads (decision 0029). Shared by the path on the home screen and the
 * "Up next" that ends every activity, so finishing one thing always hands the learner the next. */
import type { TFunction } from "i18next";
import { router } from "expo-router";

import type { ApiClient } from "@/api/client";
import type { PathStop } from "@/api/types";
import { openKeyPoint } from "@/school/keyPoints";
import type { IconName } from "@/ui/kit";

export const STOP_ICONS: Record<PathStop["kind"], IconName> = {
  warmup: "flash",
  fix: "construct",
  story: "chatbubbles",
  sounds: "mic",
  learn: "book",
};

/** ``story``: how the story stop is named where it is shown ("Continue day 7" on the home screen). */
export function stopTitle(t: TFunction, stop: PathStop, story = t("path.story.title")): string {
  switch (stop.kind) {
    case "warmup":
      return t("path.warmup.title");
    case "story":
      return story;
    case "sounds":
      return t("path.sounds.title", { example: stop.example ?? "" });
    case "fix":
      return t("path.fix.title", { title: stop.title ?? "" });
    default:
      return stop.title ? t("path.learn.title", { title: stop.title }) : t("path.learn.done");
  }
}

/** Why the coach picked this stop, in one sentence drawn from what the learner has shown. */
export function stopWhy(t: TFunction, stop: PathStop): string {
  if (stop.why) return stop.why;
  switch (stop.kind) {
    case "warmup":
      return t("path.warmup.why", { count: stop.count ?? 0 });
    case "story":
      return t("path.story.why");
    case "sounds":
      return t("path.sounds.why", { title: stop.title ?? "" });
    case "fix":
      return stop.better ? t("path.fix.why", { said: stop.said, better: stop.better }) : t("path.fix.whySaid", { said: stop.said });
    default:
      return t("path.learn.why");
  }
}

/** Opens a stop. The story starts from the home screen, which plans the day; ``onStory`` is that, when already there. */
export async function openStop(api: ApiClient, stop: PathStop, onStory?: () => void): Promise<void> {
  switch (stop.kind) {
    case "warmup":
      return router.push("/phone");
    case "story":
      return onStory ? onStory() : router.navigate("/(tabs)/city");
    case "sounds":
      return stop.drill ? router.push({ pathname: "/studio/[key]", params: { key: stop.drill } }) : router.push("/studio");
    default:
      if (!stop.node_key) return router.push("/school");
      return openKeyPoint(api, stop.node_key).catch(() => router.push("/school"));
  }
}
