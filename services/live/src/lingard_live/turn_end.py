"""Semantic end of turn (SPEC §6.2): whether the words heard so far read as a finished utterance.

The streaming transcriber's running text is the signal. A finished question ("Est-ce qu'il y a des frais ?") hands
the floor to the NPC, so the endpointer may close the turn early, at the speculation point, instead of waiting the
learner's whole patience window. A finished statement may not: learners pause half a second between sentences and
carry on (measured live 2026-10-20: ending on any full stop cut two of three multi-sentence turns in half). A trailing
"…" or a continuation word ("et", "parce") means they are still thinking.
"""

from __future__ import annotations

from lingard_live.languages import LanguageConfig, words

FINISHED = 0.95
UNFINISHED = 0.0
CLOSERS = "\"'»”)] "


def completeness(text: str, language: LanguageConfig) -> float:
    """``FINISHED`` when ``text`` ends in a finished question in ``language``, else ``UNFINISHED``."""
    body = text.strip().rstrip(CLOSERS)
    if not body.endswith(tuple(language.question_marks)):
        return UNFINISHED
    said = words(body)
    if not said or said[-1] in language.continuation_words:
        return UNFINISHED
    return FINISHED
