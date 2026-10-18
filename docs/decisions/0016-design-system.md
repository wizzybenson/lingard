# 0016: A "travel journal" design system

- **Date:** 2026-10-18
- **Status:** accepted (reversible)

## Context

The founder: the app "looks ugly". It should look world-class, with "no overflow of texts, buttons look slick, all UI
UX clean and aesthetically pleasing and ergonomic, guiding the users".

## Decision

The direction draws on apps known for their design: Airbnb's warm editorial cards and confident type; Apple Journal
and Fitness's large titles and gradient hero cards; Duolingo's single obvious next action and progress cues; Headspace's
calm warmth. For an app about living in a city to pass a serious exam, that means a travel-journal look:

- **Tokens** (`src/ui/theme.ts`): paper `#F6F1E9`, ink `#16213A`, harbour-blue accent, sunset coral for highlights,
  soft tinted surfaces for status; Fraunces (display serif) for headings and Inter for interface text, loaded with
  expo-font; radii 10/14/20/28; soft warm shadows instead of borders.
- **Kit** (`src/ui/kit.tsx`): large-title `Screen` (with an eyebrow line), `Card` tones, `Button` kinds (one primary per
  screen; secondary, tinted and ghost below it), `ListRow` and grouped `Section` (iOS-settings style), `Segmented`,
  `Chip`, `Avatar`, `IconBubble`, `ProgressBar`, and an `ErrorText` banner with a retry.
- **Screens:** City (story-day header, greeting, Today hero, segmented city switch, map card, places as rows with icons
  and faces), Scene (portrait card, goal callout, status pill, chat-bubble captions, pinned mic and Leave), Sign-in
  (brand header, language choice), Passport, Exam Hall, Phone, School and Settings (grouped).
- **Ergonomics:** targets of at least 48 px; actions within thumb reach (pinned during live scenes); sign-in on the sixth
  PIN digit; Return moves from name to PIN; the brand folds away while the keyboard is up; scroll views inset for the
  keyboard.
- **No overflow:** row subtitles wrap instead of truncating; choices that crowd a row stack instead; shorter tab labels
  where a translation was cut ("Examens"); map labels stay inside the map. Every screen was checked at iPhone 17 Pro
  size, in English and French, with Maestro screenshots (`apps/mobile/e2e`).
- Places have a semantic `kind` in content (home, café, bank…), not an icon name, so the app picks the icon and
  content stays language-agnostic.

Not done yet: a date picker for the exam date (still typed as YYYY-MM-DD), dark mode, and redesigns of the lesson,
exam-thread, desk and notebook bodies beyond their headers.
