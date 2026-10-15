from evals.live_scenes import LEARNER_MS_PER_WORD
from evals.scenes import eval_scenes
from lingard_live.turn_gate import validate_turn


def test_simulated_learner_turns_pass_the_turn_gate() -> None:
    """The live eval once sent 2 s of audio for every turn, so the gate dropped most long learner lines as
    implausibly fast and the NPC never answered. Every simulated turn must look like real speech to the gate."""
    lines = [
        "Bonjour Nadia, merci de me recevoir. Je viens préparer une entrevue pour un poste de réceptionniste, parce "
        "que j'ai déjà travaillé dans le service à la clientèle et j'aimerais vraiment ce poste.",
        "Hi. I'd like to know what I have to bring with me to open an account, because I only moved here last month.",
        "Oui.",
    ]
    for line in lines:
        speech_ms = max(len(line.split()) * LEARNER_MS_PER_WORD, 1000)
        assert validate_turn(line, confidence=0.95, speech_ms=speech_ms, recent_npc_lines=[]).status == "accepted"


def test_every_required_grammar_target_has_a_concrete_tactic() -> None:
    for contract, _, _ in eval_scenes(18):
        tactics = {t.target: t.tactic for t in contract.elicitation}
        for spec in contract.evidence_required:
            assert not tactics[spec.target].startswith("Steer the talk"), spec.target
