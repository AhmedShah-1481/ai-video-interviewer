"""
Typed state object for the whole graph (prep phase + live call phase share
one state — this is why field docs matter, the viva will ask "what's in
your state and why is that field there").
"""
from typing import TypedDict, Literal, Optional


class Turn(TypedDict):
    speaker: Literal["agent", "candidate"]
    text: str
    timestamp_ms: int
    node: str
    interrupted: bool


class Question(TypedDict):
    id: str
    text: str
    competency: str
    source: str
    source_reference: str
    difficulty: str
    follow_up_triggers: list[str]


class InterviewState(TypedDict, total=False):
    # --- raw inputs, consumed once by the first two prep nodes then unused ---
    _jd_text_raw: str
    _resume_pdf_path: str

    # --- prep phase outputs (populated once, read-only after HITL gate) ---
    jd: dict
    resume: dict
    github_data: dict
    gap_analysis: dict
    question_plan: dict
    hitl_decision: Literal["pending", "approved", "edited", "rejected"]

    # --- live call phase ---
    current_question_index: int          # index into question_plan["questions"]
    current_question: Optional[Question]
    followup_counts: dict[str, int]      # question_id -> probes used so far, capped at MAX_FOLLOW_UP_PROBES
    last_candidate_answer: str
    last_answer_quality: Literal["shallow", "strong", "silent", "off_topic", "bluff_suspected", ""]
    transcript: list[Turn]
    interview_start_ms: int
    call_elapsed_ms: int
    barge_in_flag: bool                  # set True mid-agent-speech when candidate starts talking
    guardrail_flags: list[dict]

    # --- routing control ---
    next_node_override: Optional[str]    # set by conditional edges to force a jump (e.g. -> wrap_up on time)
    current_node: str                    # which node is executing, used by checkpointer resume-on-drop

    # --- scoring phase ---
    scorecard: Optional[dict]

    # --- candidate identity, carried through for reports ---
    candidate_name: str
    role_title: str