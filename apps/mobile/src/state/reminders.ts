/** One daily local reminder (no server push): it nudges the learner to keep the streak and do due reviews. The
 * schedule itself is the stored state, so there is nothing to sync; the text is refreshed whenever Today loads. */
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

const KIND = "lingard-daily";

export const REMINDER_TIMES = [
  { hour: 8, minute: 0 },
  { hour: 12, minute: 30 },
  { hour: 19, minute: 0 },
  { hour: 21, minute: 0 },
] as const;

export interface ReminderTime {
  hour: number;
  minute: number;
}

/** Local notifications exist on phones only. */
export const remindersSupported = Platform.OS !== "web";

export async function currentReminder(): Promise<ReminderTime | null> {
  if (!remindersSupported) return null;
  const scheduled = await Notifications.getAllScheduledNotificationsAsync();
  const ours = scheduled.find((n) => n.content.data?.kind === KIND);
  const trigger = ours?.trigger as { hour?: number; minute?: number } | undefined;
  return trigger?.hour !== undefined && trigger.minute !== undefined ? { hour: trigger.hour, minute: trigger.minute } : null;
}

async function cancel(): Promise<void> {
  const scheduled = await Notifications.getAllScheduledNotificationsAsync();
  await Promise.all(
    scheduled.filter((n) => n.content.data?.kind === KIND).map((n) => Notifications.cancelScheduledNotificationAsync(n.identifier)),
  );
}

/** Schedule (or with ``time = null`` remove) the daily reminder. Returns false if the learner denied permission. */
export async function setReminder(time: ReminderTime | null, title: string, body: string): Promise<boolean> {
  if (!remindersSupported) return false;
  await cancel();
  if (time === null) return true;
  const permission = await Notifications.requestPermissionsAsync();
  if (!permission.granted) return false;
  await Notifications.scheduleNotificationAsync({
    content: { title, body, data: { kind: KIND } },
    trigger: { type: Notifications.SchedulableTriggerInputTypes.DAILY, hour: time.hour, minute: time.minute },
  });
  return true;
}

/** Keep the time, refresh the words (e.g. "3 reviews due") without asking for permission again. */
export async function refreshReminderText(title: string, body: string): Promise<void> {
  const time = await currentReminder();
  if (time === null) return;
  await cancel();
  await Notifications.scheduleNotificationAsync({
    content: { title, body, data: { kind: KIND } },
    trigger: { type: Notifications.SchedulableTriggerInputTypes.DAILY, hour: time.hour, minute: time.minute },
  });
}

export function reminderText(t: (key: string, options?: Record<string, unknown>) => string, today: { streak: number; reviews_due: number }) {
  const title = today.streak > 0 ? t("reminders.keepStreak", { count: today.streak }) : t("reminders.startStreak");
  const body = today.reviews_due > 0 ? t("reminders.reviews", { count: today.reviews_due }) : t("reminders.story");
  return { title, body };
}
