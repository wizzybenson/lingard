import { render, screen } from "@testing-library/react-native";

import "@/i18n";
import { Music } from "@/studio/Music";
import type { Music as MusicResult } from "@/studio/types";

import questionAsStatement from "./fixtures/music_question_as_statement.json";

// A real result from the pronunciation service (2026-10-22): the model asks "Are you coming tonight?" with a rising
// voice, the take says it as a statement.
const music = questionAsStatement as unknown as MusicResult;

test("a question said as a statement is explained, with the parts of the music scored", async () => {
  await render(<Music music={music} focus="intonation" />);
  expect(screen.getByText("The music of your speech")).toBeTruthy();
  expect(screen.getByLabelText(/^Intonation: \d+ out of 100$/)).toBeTruthy();
  expect(screen.getByText("Your voice should rise at the end; it fell.")).toBeTruthy();
});
