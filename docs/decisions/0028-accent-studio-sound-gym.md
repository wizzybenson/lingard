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

`tools/voicebench/studio_robot.py` climbs drills through the running API with real speech. At every spoken stage it
also says the minimal-pair partner, then checks the mistake is caught with a tip that names it, and it checks
reviews. French: every drill climbs, scoring takes about 1.5 s per take, and the robot found and fixed four
problems:

- TTS read the single words "me" and "dessert" the English way. They were replaced by "te" and "coussin / cousin".
- The fix for the trained sound must come before tips about other sounds.
- Question phrases written without "?" had no ending to train.
- "Said well!" was shown for a contrast that can't be judged.

One recording of "su" said for "si" still passes, within that contrast's measured 8% miss rate.

## Not done here

- A recogniser trained on learner speech would sharpen the vowel contrasts; slplab's L2-English model has no
  licence.
- Commercial pronunciation-assessment APIs (Azure, Speechace) need a key and a spending decision.
- The ElevenLabs narrator's single-word renders should be audited the same way the robot audited the learner side.
