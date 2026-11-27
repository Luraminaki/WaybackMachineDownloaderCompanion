"""No function or method is more complex than radon grade B (the owner's limit)."""

from radon.complexity import cc_visit  # pyright: ignore[reportMissingTypeStubs]  # radon ships none

from tests.test_conventions import ROOT, python_files

MAX_COMPLEXITY = 10  # radon grade B upper bound; C and worse must be split


def test_no_block_exceeds_grade_b() -> None:
    """Every function, method and class stays at cyclomatic complexity 10 or below."""
    too_complex = [
        f"{path.relative_to(ROOT)}:{block.lineno} {block.name} {block.complexity}"
        for path in python_files()
        for block in cc_visit(path.read_text(encoding="utf-8"))
        if block.complexity > MAX_COMPLEXITY
    ]
    assert too_complex == []


def test_planted_complex_function_is_found() -> None:
    """Complexity 11 (ten branches) is over the limit, 10 (nine branches) is not."""
    branches = "".join(f"    if x == {n}:\n        return {n}\n" for n in range(9))
    blocks = cc_visit(
        f"def at_limit(x):\n{branches}\ndef over(x):\n{branches}    if x:\n        x = 0\n"
    )

    assert {block.name: block.complexity > MAX_COMPLEXITY for block in blocks} == {
        "at_limit": False,
        "over": True,
    }
