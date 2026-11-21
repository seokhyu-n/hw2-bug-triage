import pytest

from app import prompts
from app.pipeline import BASELINE, PipelineConfig

STEPS = ["extract", "classify", "link", "score"]
SECTIONS = ["# Task", "# Context", "# Constraints", "# Input", "# Output format", "# Success criteria"]


def test_build_system_order_and_cache_marker():
    blocks = prompts.build_system("score", PipelineConfig())
    assert "Rubric" in blocks[-1]["text"] and blocks[-1]["cache_control"] == {"type": "ephemeral"}


def test_build_system_baseline_has_no_examples():
    assert all("Example" not in b["text"] for b in prompts.build_system("classify", BASELINE))


@pytest.mark.parametrize("step", STEPS)
def test_only_last_block_has_cache_marker(step):
    blocks = prompts.build_system(step, PipelineConfig())
    assert blocks[-1]["cache_control"] == {"type": "ephemeral"}
    assert all("cache_control" not in b for b in blocks[:-1])
    assert all(b["type"] == "text" and b["text"].strip() for b in blocks)


@pytest.mark.parametrize("step", STEPS)
def test_base_prompt_has_markdown_template_sections(step):
    base = prompts.build_system(step, BASELINE)[0]["text"]
    for section in SECTIONS:
        assert section in base, f"{step}: {section} 누락"


def test_full_config_order_rules_then_examples_then_rubric():
    blocks = prompts.build_system("score", PipelineConfig())
    assert len(blocks) == 3
    assert "# Task" in blocks[0]["text"]
    assert "## Example 1" in blocks[1]["text"]
    assert "Rubric" in blocks[2]["text"]


def test_rubric_only_for_score_and_only_when_enabled():
    assert all("Rubric" not in b["text"] for b in prompts.build_system("score", BASELINE))
    assert all("Rubric" not in b["text"] for b in prompts.build_system("classify", PipelineConfig()))


def test_classify_fewshot_covers_boundary_cases():
    text = "".join(b["text"] for b in prompts.build_system("classify", PipelineConfig()))
    for phrase in ["GPS 기록", "기록 내보내기", "체중 설정", "카드 저장"]:
        assert phrase in text
    assert text.count("## Example") >= 4


def test_link_has_no_examples_block():
    assert len(prompts.build_system("link", PipelineConfig())) == 1


def test_system_is_byte_stable_between_calls():
    assert prompts.build_system("extract", PipelineConfig()) == prompts.build_system("extract", PipelineConfig())
