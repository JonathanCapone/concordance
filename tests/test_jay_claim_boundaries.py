"""Jay must not silently reintroduce claims narrowed in the application."""

from concordance.jay import SYSTEM, build_tools
from concordance.tools import Corpus


def test_system_prompt_uses_the_scoped_current_benchmark() -> None:
    assert "96.8% precision on four pages" in SYSTEM
    assert "68 gold values" in SYSTEM
    assert "89%" not in SYSTEM
    assert "corpus-wide guarantee" in SYSTEM


def test_tool_copy_preserves_silence_and_citation_boundaries() -> None:
    tools = build_tools(Corpus([], []))
    quiet = tools["what_went_quiet"].description.lower()
    paper = tools["show_the_paper"].description.lower()
    disputed = tools["what_is_disputed"].description.lower()

    assert "collection-wide scanning stop" in quiet
    assert "does not explain any individual place gap" in quiet
    assert "when the image service and word boxes allow" in paper
    assert "does not settle whether its interpretation is correct" in paper
    assert "crop when available" in disputed
