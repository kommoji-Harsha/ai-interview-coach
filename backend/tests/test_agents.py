"""Unit tests for Phase 2 agents: Interviewer, Scorer, and Feedback agents with mocked LLM."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agents import (
    CALIBRATION_QUESTION_BANK,
    DEFAULT_RUBRIC_BY_TOPIC,
    DimensionScore,
    FeedbackAgent,
    FeedbackInput,
    FeedbackResponse,
    InterviewerAgent,
    InterviewerInput,
    InterviewerResponse,
    ScorerAgent,
    ScoreResponse,
    ScorerInput,
    TurnData,
    TurnScores,
    adapt_difficulty,
    generate_template_feedback,
    infer_seniority_difficulty,
    is_obvious_no_answer,
    resolve_rubric_dimensions,
    select_next_topic,
)
from backend.agents.base import extract_json_payload
from backend.agents.prompt_loader import load_prompt_file, parse_prompt_sections, render_template
from backend.gateway.client import LLMGateway
from backend.gateway.models import LLMResult


@pytest.fixture
def mock_gateway():
    """Create a mock LLMGateway."""
    gateway = MagicMock(spec=LLMGateway)
    gateway.complete = AsyncMock()
    return gateway


# ---------------------------------------------------------------------------
# Prompt Loader Tests
# ---------------------------------------------------------------------------


def test_prompt_loader_and_parser():
    """Verify loading prompt files and splitting system/user sections."""
    for agent_name in ["interviewer", "scorer", "feedback"]:
        content = load_prompt_file(agent_name, "v1")
        system_sec, user_sec = parse_prompt_sections(content)
        assert len(system_sec) > 0
        assert len(user_sec) > 0

    rendered = render_template("Hello {{name}}! Score: {{score}}", {"name": "Alice", "score": 5})
    assert rendered == "Hello Alice! Score: 5"


def test_extract_json_payload():
    """Verify extracting JSON from plain text and markdown fences."""
    raw_plain = '{"key": "value"}'
    assert extract_json_payload(raw_plain) == '{"key": "value"}'

    raw_fence = '```json\n{"key": "value"}\n```'
    assert extract_json_payload(raw_fence) == '{"key": "value"}'

    raw_with_text = 'Here is the response:\n```json\n{"key": "value"}\n```\nHope that helps!'
    assert extract_json_payload(raw_with_text) == '{"key": "value"}'

    raw_unfenced_with_text = 'Response: {"key": "value"} is complete.'
    assert extract_json_payload(raw_unfenced_with_text) == '{"key": "value"}'


# ---------------------------------------------------------------------------
# Interviewer Agent Tests
# ---------------------------------------------------------------------------


def test_difficulty_adaptation():
    """Verify difficulty adaptation rules."""
    # Increases if recent avg >= 4.0
    assert adapt_difficulty(3, [4.0, 4.5]) == 4
    assert adapt_difficulty(5, [5.0, 5.0]) == 5  # Cap at 5

    # Decreases if recent avg <= 2.0
    assert adapt_difficulty(3, [2.0, 1.5]) == 2
    assert adapt_difficulty(1, [1.0, 2.0]) == 1  # Floor at 1

    # Unchanged otherwise
    assert adapt_difficulty(3, [3.0, 3.5]) == 3
    assert adapt_difficulty(3, []) == 3


def test_infer_seniority_difficulty():
    """Verify initial difficulty inference from JD seniority level."""
    assert infer_seniority_difficulty("We are hiring an Associate / Junior Backend Engineer") == 2
    assert infer_seniority_difficulty("Looking for a Mid-level Software Developer") == 3
    assert infer_seniority_difficulty("Senior Software Engineer with 7+ years experience") == 4
    assert infer_seniority_difficulty("Staff Distributed Systems Architect") == 5


def test_topic_selection():
    """Verify topic coverage tracking and selection."""
    # Prioritizes uncovered focus topic
    focus = ["system-design", "behavioral"]
    assert select_next_topic(topics_covered=["behavioral"], focus_topics=focus) == "system-design"

    # Next uncovered from universe
    covered = ["behavioral", "technical"]
    next_topic = select_next_topic(topics_covered=covered)
    assert next_topic == "system-design"

    # All covered: picks weakest topic from scores_so_far
    all_covered = [
        "behavioral",
        "technical",
        "system-design",
        "problem-solving",
        "culture-fit",
        "domain-specific",
    ]
    scores = [
        {"topic": "behavioral", "score": 4.5},
        {"topic": "system-design", "score": 2.0},
        {"topic": "technical", "score": 3.5},
    ]
    weakest = select_next_topic(topics_covered=all_covered, scores_so_far=scores)
    assert weakest == "system-design"


@pytest.mark.asyncio
async def test_interviewer_question_generation_happy_path(mock_gateway):
    """Interviewer generates next question and parses valid response."""
    valid_llm_json = json.dumps(
        {
            "question": "Can you walk me through how you designed the caching layer at your previous company?",
            "topic": "system-design",
            "subtopic": "caching",
            "difficulty": 3,
            "reasoning": "Candidate mentioned Redis on their resume; assessing depth.",
            "is_follow_up": False,
        }
    )
    mock_gateway.complete.return_value = LLMResult(
        content=valid_llm_json,
        model="gpt-4o",
        provider="openai",
    )

    agent = InterviewerAgent(gateway=mock_gateway)
    input_data = InterviewerInput(
        resume_text="Senior backend engineer with Redis experience",
        jd_text="Staff engineer needed",
        conversation_history=[
            TurnData(turn_number=1, role="interviewer", content="Tell me about your background."),
            TurnData(
                turn_number=2, role="candidate", content="I worked on high-scale caching at Acme."
            ),
        ],
        topics_covered=["behavioral"],
        difficulty_level=3,
        turn_number=3,
        max_turns=6,
    )

    response = await agent.run(input_data)
    assert isinstance(response, InterviewerResponse)
    assert "caching layer" in response.question
    assert response.topic == "system-design"
    assert response.difficulty == 3
    assert not response.is_follow_up
    assert response.source == "llm"

    # Verify resume and JD are isolated in user message
    call_args = mock_gateway.complete.call_args[1]
    messages = call_args["messages"]
    system_msg = next(m for m in messages if m.role == "system")
    user_msg = next(m for m in messages if m.role == "user")
    assert "<resume>" in user_msg.content
    assert "Senior backend engineer" in user_msg.content
    assert "<job_description>" in user_msg.content
    assert "<resume>" not in system_msg.content


@pytest.mark.asyncio
async def test_interviewer_follow_up_generation(mock_gateway):
    """Interviewer generates a follow-up probing a previous answer."""
    follow_up_json = json.dumps(
        {
            "question": "You mentioned using write-through caching. How did you handle cache invalidation during race conditions?",
            "topic": "system-design",
            "subtopic": "cache-invalidation",
            "difficulty": 4,
            "reasoning": "Candidate gave a high-level answer on caching; probing deeper into consistency.",
            "is_follow_up": True,
        }
    )
    mock_gateway.complete.return_value = LLMResult(
        content=follow_up_json,
        model="gpt-4o",
        provider="openai",
    )

    agent = InterviewerAgent(gateway=mock_gateway)
    input_data = InterviewerInput(
        resume_text="Redis expert",
        jd_text="Lead engineer",
        conversation_history=[
            TurnData(
                turn_number=1, role="interviewer", content="How do you handle high read traffic?"
            ),
            TurnData(
                turn_number=2,
                role="candidate",
                content="We implemented a write-through Redis cache.",
            ),
        ],
        topics_covered=["system-design"],
        difficulty_level=4,
        turn_number=3,
        max_turns=6,
    )

    response = await agent.run(input_data)
    assert response.is_follow_up is True
    assert "cache invalidation" in response.question


@pytest.mark.asyncio
async def test_interviewer_retry_on_invalid_json(mock_gateway):
    """Interviewer retries when LLM returns invalid JSON on first attempt."""
    invalid_response = "I will ask: Tell me about your distributed systems experience."
    valid_json = json.dumps(
        {
            "question": "Can you describe how you architected a distributed queue?",
            "topic": "system-design",
            "subtopic": "messaging",
            "difficulty": 3,
            "reasoning": "Valid structured question after retry.",
            "is_follow_up": False,
        }
    )

    mock_gateway.complete.side_effect = [
        LLMResult(content=invalid_response, model="gpt-4o", provider="openai"),
        LLMResult(content=valid_json, model="gpt-4o", provider="openai"),
    ]

    agent = InterviewerAgent(gateway=mock_gateway, max_retries=2)
    input_data = InterviewerInput(
        resume_text="Software Engineer",
        jd_text="Backend Developer",
        topics_covered=[],
        difficulty_level=3,
        turn_number=1,
    )

    response = await agent.run(input_data)
    assert response.question == "Can you describe how you architected a distributed queue?"
    assert mock_gateway.complete.call_count == 2

    # Second call includes error feedback
    second_call_messages = mock_gateway.complete.call_args_list[1][1]["messages"]
    assert any("Your previous response was invalid" in m.content for m in second_call_messages)


@pytest.mark.asyncio
async def test_interviewer_fallback_to_question_bank(mock_gateway):
    """Interviewer falls back to question bank when all retries are exhausted."""
    # Always return broken output
    mock_gateway.complete.return_value = LLMResult(
        content="not valid json at all",
        model="gpt-4o",
        provider="openai",
    )

    agent = InterviewerAgent(gateway=mock_gateway, max_retries=1)
    input_data = InterviewerInput(
        resume_text="Engineer",
        jd_text="Backend Engineer",
        difficulty_level=4,
        turn_number=1,
    )

    response = await agent.run(input_data)
    assert isinstance(response, InterviewerResponse)
    assert response.source == "question_bank"
    assert response.difficulty == 4
    assert response.question in CALIBRATION_QUESTION_BANK[4]


# ---------------------------------------------------------------------------
# Scorer Agent Tests
# ---------------------------------------------------------------------------


def test_resolve_rubric_dimensions():
    """Verify rubric dimensions selection per topic."""
    assert resolve_rubric_dimensions("behavioral") == DEFAULT_RUBRIC_BY_TOPIC["behavioral"]
    assert resolve_rubric_dimensions("system-design") == DEFAULT_RUBRIC_BY_TOPIC["system-design"]
    assert resolve_rubric_dimensions("unknown-topic") == [
        "communication",
        "relevance",
        "technical_depth",
    ]
    # Explicit override
    custom = ["leadership", "grit"]
    assert resolve_rubric_dimensions("behavioral", custom) == custom


def test_obvious_no_answer_check():
    """Verify fast-path recognition for candidate skips or empty answers."""
    assert is_obvious_no_answer("") is True
    assert is_obvious_no_answer("   ") is True
    assert is_obvious_no_answer("i don't know") is True
    assert is_obvious_no_answer("idk") is True
    assert is_obvious_no_answer("skip") is True
    assert is_obvious_no_answer("pass") is True
    assert is_obvious_no_answer("I designed a high throughput Kafka queue") is False


@pytest.mark.asyncio
async def test_scorer_fast_path_no_answer(mock_gateway):
    """Scorer uses fast-path without calling LLM for explicit skips."""
    agent = ScorerAgent(gateway=mock_gateway)
    input_data = ScorerInput(
        question="Explain how Paxos consensus works.",
        answer="I don't know, can we skip this?",
        topic="system-design",
    )

    response = await agent.run(input_data)
    assert response.answer_type == "no_answer"
    assert len(response.scores) == 5  # system-design has 5 dimensions
    for score in response.scores:
        assert score.score == 1
        assert "Not addressed" in score.evidence
        assert score.confidence == 1.0
    # No LLM call was needed
    assert mock_gateway.complete.call_count == 0


@pytest.mark.asyncio
async def test_scorer_rubric_scoring_happy_path(mock_gateway):
    """Scorer evaluates answer on dimensions with evidence and confidence."""
    score_json = json.dumps(
        {
            "answer_type": "attempted",
            "scores": [
                {
                    "dimension": "communication",
                    "score": 4,
                    "evidence": "Candidate structured response with Situation, Task, Action, Result.",
                    "confidence": 0.9,
                },
                {
                    "dimension": "relevance",
                    "score": 5,
                    "evidence": "Addressed conflict resolution directly: 'I scheduled a 1-on-1 to align on goals.'",
                    "confidence": 0.85,
                },
                {
                    "dimension": "examples",
                    "score": 4,
                    "evidence": "Shared a specific example involving a dispute over REST vs GraphQL.",
                    "confidence": 0.8,
                },
            ],
            "overall_impression": "Strong, structured answer with concrete conflict-resolution examples.",
        }
    )
    mock_gateway.complete.return_value = LLMResult(
        content=score_json,
        model="gpt-4o",
        provider="openai",
    )

    agent = ScorerAgent(gateway=mock_gateway)
    input_data = ScorerInput(
        question="Tell me about a technical disagreement with a teammate.",
        answer="In my last role, we disagreed on REST vs GraphQL. I scheduled a 1-on-1 to align on goals and we compromised.",
        topic="behavioral",
    )

    response = await agent.run(input_data)
    assert isinstance(response, ScoreResponse)
    assert response.answer_type == "attempted"
    assert len(response.scores) == 3
    comm_score = next(s for s in response.scores if s.dimension == "communication")
    assert comm_score.score == 4
    assert comm_score.confidence == 0.9
    assert comm_score.needs_review is False
    assert "STAR" in comm_score.evidence or "Situation" in comm_score.evidence


@pytest.mark.asyncio
async def test_scorer_low_confidence_flag(mock_gateway):
    """Scorer sets needs_review = True when dimension confidence is < 0.6."""
    score_json = json.dumps(
        {
            "answer_type": "attempted",
            "scores": [
                {
                    "dimension": "communication",
                    "score": 3,
                    "evidence": "Answer was somewhat concise.",
                    "confidence": 0.5,  # Low confidence!
                },
                {
                    "dimension": "relevance",
                    "score": 4,
                    "evidence": "Directly answered.",
                    "confidence": 0.8,
                },
                {
                    "dimension": "examples",
                    "score": 3,
                    "evidence": "Brief mention of past work.",
                    "confidence": 0.7,
                },
            ],
            "overall_impression": "Decent answer but ambiguous communication depth.",
        }
    )
    mock_gateway.complete.return_value = LLMResult(
        content=score_json,
        model="gpt-4o",
        provider="openai",
    )

    agent = ScorerAgent(gateway=mock_gateway)
    input_data = ScorerInput(
        question="Describe a challenge.",
        answer="It was tricky but we managed.",
        topic="behavioral",
    )

    response = await agent.run(input_data)
    comm_score = next(s for s in response.scores if s.dimension == "communication")
    assert comm_score.needs_review is True
    rel_score = next(s for s in response.scores if s.dimension == "relevance")
    assert rel_score.needs_review is False


@pytest.mark.asyncio
async def test_scorer_retry_on_missing_dimensions(mock_gateway):
    """Scorer retries if LLM forgets one of the requested dimensions."""
    # Attempt 1: only scores 2 of 3 dimensions
    missing_dim_json = json.dumps(
        {
            "answer_type": "attempted",
            "scores": [
                {"dimension": "communication", "score": 4, "evidence": "good", "confidence": 0.9},
                {"dimension": "relevance", "score": 4, "evidence": "on point", "confidence": 0.9},
            ],
            "overall_impression": "Forgot examples dimension.",
        }
    )
    # Attempt 2: scores all 3 dimensions
    full_json = json.dumps(
        {
            "answer_type": "attempted",
            "scores": [
                {"dimension": "communication", "score": 4, "evidence": "good", "confidence": 0.9},
                {"dimension": "relevance", "score": 4, "evidence": "on point", "confidence": 0.9},
                {"dimension": "examples", "score": 4, "evidence": "concrete", "confidence": 0.85},
            ],
            "overall_impression": "Complete score.",
        }
    )

    mock_gateway.complete.side_effect = [
        LLMResult(content=missing_dim_json, model="gpt-4o", provider="openai"),
        LLMResult(content=full_json, model="gpt-4o", provider="openai"),
    ]

    agent = ScorerAgent(gateway=mock_gateway, max_retries=2)
    input_data = ScorerInput(
        question="Tell me about a conflict.",
        answer="We had a debate and resolved it using benchmarks.",
        topic="behavioral",
    )

    response = await agent.run(input_data)
    assert len(response.scores) == 3
    assert mock_gateway.complete.call_count == 2


# ---------------------------------------------------------------------------
# Feedback Agent Tests
# ---------------------------------------------------------------------------


def test_template_feedback_generation():
    """Verify deterministic template feedback generation."""
    turns = [
        TurnData(turn_number=1, role="interviewer", content="Q1"),
        TurnData(turn_number=2, role="candidate", content="A1"),
    ]
    # High scores -> interview_ready
    high_feedback = generate_template_feedback(
        aggregate_scores={"communication": 4.5, "technical_depth": 4.2, "overall": 4.3},
        turns=turns,
    )
    assert high_feedback.estimated_readiness == "interview_ready"
    assert high_feedback.feedback_source == "template"
    assert len(high_feedback.strengths) >= 1

    # Low scores -> needs_work
    low_feedback = generate_template_feedback(
        aggregate_scores={"communication": 2.0, "technical_depth": 1.8, "overall": 1.9},
        turns=turns,
    )
    assert low_feedback.estimated_readiness == "needs_work"
    assert len(low_feedback.improvements) >= 1
    assert len(low_feedback.action_items) >= 1


@pytest.mark.asyncio
async def test_feedback_agent_happy_path(mock_gateway):
    """FeedbackAgent generates structured post-interview feedback."""
    feedback_json = json.dumps(
        {
            "summary": "The candidate demonstrated solid technical and architectural fundamentals with clear STAR structuring in behavioral questions.",
            "strengths": [
                "Clear STAR method articulation in turn 2",
                "Strong understanding of Redis caching strategies in turn 4",
            ],
            "improvements": [
                "Proactively address data consistency and network partitioning edge cases in system design",
                "Quantify impact with concrete business or latency metrics",
            ],
            "action_items": [
                "Practice designing distributed caches under a 15-minute timer",
                "Prepare 3 concrete examples illustrating architectural trade-offs",
            ],
            "recommended_topics": ["system-design", "distributed-consensus"],
            "estimated_readiness": "progressing",
        }
    )
    mock_gateway.complete.return_value = LLMResult(
        content=feedback_json,
        model="gpt-4o",
        provider="openai",
    )

    agent = FeedbackAgent(gateway=mock_gateway)
    input_data = FeedbackInput(
        turns=[
            TurnData(turn_number=1, role="interviewer", content="Tell me about a time you led."),
            TurnData(turn_number=2, role="candidate", content="I led the migration at Acme."),
        ],
        scores=[
            TurnScores(
                turn_number=2,
                scores=[
                    DimensionScore(
                        dimension="communication",
                        score=4,
                        evidence="Structured",
                        confidence=0.9,
                    )
                ],
            )
        ],
        aggregate_scores={"communication": 4.0, "overall": 4.0},
    )

    response = await agent.run(input_data)
    assert isinstance(response, FeedbackResponse)
    assert response.estimated_readiness == "progressing"
    assert len(response.strengths) == 2
    assert len(response.improvements) == 2
    assert len(response.action_items) == 2
    assert "system-design" in response.recommended_topics
    assert response.feedback_source == "llm"


@pytest.mark.asyncio
async def test_feedback_agent_validation_overlap_check():
    """FeedbackResponse validator rejects exact overlap between strengths and improvements."""
    with pytest.raises(ValueError, match="overlap"):
        FeedbackResponse(
            summary="Session summary",
            strengths=["Communication"],
            improvements=["Communication"],  # Exact overlap!
            action_items=["Practice"],
            recommended_topics=["behavioral"],
            estimated_readiness="progressing",
        )


@pytest.mark.asyncio
async def test_feedback_agent_fallback_on_llm_failure(mock_gateway):
    """FeedbackAgent falls back to template feedback when LLM repeatedly fails."""
    mock_gateway.complete.return_value = LLMResult(
        content="corrupted invalid response",
        model="gpt-4o",
        provider="openai",
    )

    agent = FeedbackAgent(gateway=mock_gateway, max_retries=1)
    input_data = FeedbackInput(
        turns=[
            TurnData(turn_number=1, role="interviewer", content="Q1"),
            TurnData(turn_number=2, role="candidate", content="A1"),
        ],
        aggregate_scores={"communication": 4.2, "relevance": 4.0, "overall": 4.1},
    )

    response = await agent.run(input_data)
    assert isinstance(response, FeedbackResponse)
    assert response.feedback_source == "template"
    assert response.estimated_readiness == "interview_ready"
