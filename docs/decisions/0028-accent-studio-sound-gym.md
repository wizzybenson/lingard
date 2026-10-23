# 0028: Accent Studio becomes a sound gym, with measured scoring

Date: 2026-10-22. Status: accepted.

## Why

The founder asked for an accent trainer strong enough to change an accent completely. That means:

- recordings that are never lost when a connection drops;
- slowed-down listening;
- highlighting of exactly what went wrong;
- mouth and tongue guidance;
- training that sticks;
- the learner's own voice as the model (self voice transformation);
- every part of an accent: sounds, word stress, sentence emphasis, rhythm and intonation.

The old studio had 5 lines per language and scores with no guidance. Measured against native speech, those scores
were wrong much of the time.

## What the studio is now

- **Content.** `content/pronunciation/sounds_<lang>.yaml` covers every sound of each language: French 31, British
  English 43. For each sound it gives:
  - how it is made (lips, tongue, jaw, voice, air, steps and a self-check), in English and French;
  - a fix for each sound it is commonly mistaken for;
  - phonological features for the mouth map.
- **Drills.** French has 23 drills and English 26. Each drill is climbed in this order: learn → hear the
  difference (8-question minimal-pair quiz, 7 right to pass) → words → pairs → phrases → sentence.
  - Reviews come at 2, 5, 12, 30 and 75 days. A review that slips sends the drill back to its words.
  - A daily workout picks reviews that are due, then drills already begun (weakest first), then new ones.
- **Music drills.** Music drills (`focus:`) train word stress, emphasis, rhythm or intonation. French judges
  emphasis, rhythm and intonation, since it has no lexical word stress. New drills: English rhythm ("cats chase
  mice"), and French statement against question.
- **The app.**
  - Playback at 0.5×, 0.75× and 1× keeps the pitch.
  - "Hear yourself" plays the learner's own take.
  - Words are coloured by score; tapping a word shows its sounds and what each was heard as.
  - The mouth map shows the target and the sound produced, with an arrow between them.
  - Tips for exactly what was heard come first, and the music view adds scores, a syllable strip and a melody line.
  - Models are rendered in the learner's cloned voice when they have one (the golden self).
- **Recordings.** Every take is saved to the device before upload. A failed send waits there, survives the app
  closing, and is sent again with one tap (`savedRecordings.ts`). Exam speaking answers get the same.
- **Focus language** (commit 53fe5f5). One choice of French or English drives every screen.

## Scoring, and the evidence behind it

Native recordings came from three OpenAI voices and the ElevenLabs narrator (`~/.cache/lingard/calibration`, never
committed).

1. **Recognisers** (`content/pronunciation/recognizers.yaml`). Phoneme error rate on native speech of the gym's
   words:
   - French: bofenghuang/phonemizer-wav2vec2-ctc-french 15–25%, against 38–58% for the multilingual models.
   - English: wav2vec2-lv-60-espeak-cv-ft 22–27%, the best of three tried.
   - Every recogniser hears the OpenAI voices more accurately than the ElevenLabs narrator. ElevenLabs stays the
     learner's model voice, because only it can speak in their clone; calibration uses both.
2. **Lexicons** (`tools/content_cli/lexicon.py`). Generated from espeak-ng into each recogniser's own symbols.
   Phrases keep liaison and word boundaries. Optional liaisons and English function-word run-ons are fixed by hand
   in the override files.
3. **Calibration** (`tools/content_cli/calibrate.py`).
   - Sound scores are relative to native GOP percentiles.
   - Each minimal pair gets a two-way test, measured both ways.
   - French: 33 of 39 contrasts are separated at 80–100% (é/è, o/ɔ and an/in are not).
   - English: 41 of 45 (ee/eye and not/note are not).
   - Unreliable contrasts are marked to compare by ear and never scored as wrong. The screen says so ("Clear.
     Now compare the trained sound by ear").
4. **Decision rule.** On 255 native French takes each way:
   - the two-way test or the native score alone passes 82% of native speech;
   - marking a sound wrong only when both fail passes 90% and still catches 88% of substitutions.
   - That rule is used, because telling a learner who said it right that they were wrong does more harm.
5. **Music of speech.**
   - Each syllable gets the stretch of audio between its neighbours, because a CTC recogniser only marks a spike.
   - Scores are relative to how much native voices differ from each other.
   - Word stress is judged only on words where the detector finds the dictionary stress in at least 3 of 4 native
     recordings (37 English words). The stress weights (pitch 2, loudness 0.5, length 0.5, final syllable discounted)
     were fitted on 185 native renders: 79% correct, against 72% with equal weights.
   - A melody drill's ending is fixed by its text (yes/no question rises, statement falls). Its model is rendered
     with instructions and kept only once the rise or fall is measured in it: the everyday narrator read
     "Vous avez une chambre ?" flat.

## Robot evidence

`tools/voicebench/studio_robot.py` climbs drills through the running API with real speech. At each spoken rung it
also says the classic mistake (the minimal-pair partner) and checks it is caught with a tip that names it. It then
holds and slips a review.

**Final pass, 2026-10-22:**

- French: 23 of 23 drills climbed, and all 12 mistakes were caught with the right fix (é/è by ear, as designed).
- English: the one drill that had failed now climbs; every drill passes apart from a single near-miss.
  - 13 mistakes were caught, and h-dropping and not/note are marked "compare by ear".
  - One "pan" said for "pen" passed. That contrast catches 81% natively, so it is not one that decides alone.
- Scoring: median 1.4–1.5 s per take, never over 2.2 s once melody models are warmed.

**Bugs the robot found and fixed:**

- Words TTS reads the English way were replaced: "me", "dessert", "use", "new".
- "thank" was dropped: native takes of it were heard with a t.
- The fix for the trained sound now comes first, and names the partner actually heard.
- Contrasts measured on four takes were wrongly trusted. Calibration now needs 8 takes a side to trust a contrast
  and 12 to let it decide alone, and pairs were added until it had them.
- The "decides alone" flag was never loaded.
- Stress was held to one model's reading of "important". It is now held to the dictionary.
- Emphasis blocked climbs even though native voices differ. It is now shown but never blocks.
- Melody models were rendered on a learner's first take (10 s). `cli warm-studio` now renders and verifies them
  ahead of time, and a text without a verified model is left out.
- "Said well!" was shown for a by-ear contrast.

**Scene robot:** first NPC audio 1.45–1.9 s per turn. NPC replies ran to five sentences, so the live loop now
stops after three (two at band 5 and below).

**Maestro (free flows on the Simulator):** tour, review (formerly phone), school, mock, language, studio, learn-first
and errors all pass.

## Not done here

- A recogniser trained on learner speech would sharpen the vowel contrasts; slplab's L2-English model has no
  licence.
- Commercial pronunciation-assessment APIs (Azure, Speechace) need a key and a spending decision.

## Model recordings audited (2026-10-22, later)

`tools/voicebench/model_audit.py` sends each drill text's model, the recording a learner imitates, back through
scoring as if a learner had said it (`--texts` limits it to a few texts, since every new text costs a narrator render).

- French: 15 of 345 narrator models were judged wrong. English: 15 of 410. The scorer itself is deterministic: the
  same recording scored three times got the same verdict each time.
- Fix: every drill model is now checked before it is relied on (`check_model` in the studio routes).
  - The narrator's render is kept if the scorer passes it.
  - Otherwise up to three other native renders (OpenAI, the narrator voice) are tried, and the first that passes is
    kept and served instead.
  - If none passes, the text is left out of its drill. A melody text without a verified model was already left out.
- When checks run:
  - each text is checked in the background the first time it is heard, when its narrator render already exists, so
    checking adds no narration cost;
  - `cli warm-studio` checks everything up front.
- Result: on a re-run of every text that failed, both languages had 0 wrong. French "bain / banc" and "table" found
  no passing model and are left out.
- Found on the way: `OBJECT_STORE_URL` was empty in the local `.env`. The API kept every render in memory, lost it on
  each restart (and paid to render it again), and `warm-studio`'s work vanished when it exited. The local `.env` now
  points at the SeaweedFS in compose. The API tests now set `object_store_url=None` and `openai_api_key=None`, because
  importing the API loads `.env`.

## Stray sounds in model recordings (2026-10-23)

The founder heard "rue" with something before it.

**What was wrong:**
- The narrator's "rue" had about 0.3 s of sound before the word. The checks passed it because the scorer only
  measures how well the expected sounds match, so it can't hear what is extra.
- Every engine adds stray sounds to short words at random: a breath or "euh" before, an "e" after. On 24 single
  French words, about 1 in 6 to 1 in 12 had them, whether rendered by ElevenLabs flash, flash with surrounding context
  (`previous_text`), multilingual_v2 or OpenAI.
- OpenAI transcription can't serve as the judge: on known-good isolated words it was right 2 to 5 times in 12.

**The check:**
- The recogniser is decoded with no text to expect (`recognizer.heard`, greedy CTC). `/heard` aligns what it heard
  with the text by edit distance and reports sounds beyond either end.
  - A sound heard differently inside the word is left to the scorer.
  - A tie at an edge counts as extra.
  - The expected sounds are written as the recogniser writes them (a nasal vowel as vowel + tilde).
  - An n, m, ŋ or ɲ heard against a nasal vowel is its nasality, not an extra.
- The decoder and the transcriber independently heard extras in "rue", "roue" and "tu", and none in "vue" or "su".

**The fix:**
- A drill text's model is checked **before anyone hears it** (once per text, then cached):
  1. it must be clean of extras and pass the scorer;
  2. otherwise up to 3 narrator takes (`narrate(..., take=n)`), then up to 3 OpenAI takes, keeping the first that
     passes;
  3. otherwise the text is left out of its drill.
- Melody models must be clean too. `CHECK_EDITION` 4 re-checks everything checked before.
- On the Simulator: 17 French and English words, nasal ones included, all came back clean. "rue" needed retakes
  (13 s the first time, once).
- Studio audio is now served with an ETag and `no-cache`, so a re-recorded model reaches devices at once. The app's
  model URLs carry an edition (`MODEL_EDITION` 2), so a device doesn't keep the old "rue" it cached for a day.

