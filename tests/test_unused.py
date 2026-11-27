"""No dead code: every definition is used by the code it belongs to.

Every function, class, method and module-level constant of the product (the package under
``src/``) is referenced by the product; one only the tests use belongs in a test helper
module. A helper of ``tests/`` is referenced by some test, and a fixture is requested by some
test's or fixture's parameter. A reference is a name, an attribute, an import, or a word of a
string (annotations in quotes, names looked up by ``getattr``), but never a docstring's word nor
a use inside the definition itself (a function that only calls itself is still dead). Special
methods and tests are exempt, and so are the definitions a framework calls without the project
naming them: :data:`FRAMEWORK_HOOKS` methods and autouse fixtures.
"""

import ast
import re
from collections import Counter
from typing import TYPE_CHECKING

from tests.test_conventions import ROOT, decorator_names, is_test_path, python_files

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

#: Methods a library calls by name: ``html.parser.HTMLParser.feed`` dispatches each start
#: tag to ``handle_starttag``, and ``ast.NodeTransformer.visit`` each name to ``visit_Name``
#: (the duplication test's renamer).
FRAMEWORK_HOOKS = {"handle_starttag", "visit_Name"}
#: pytest fixtures are used by parameter name, not called: see :func:`unrequested_fixtures`.
FIXTURE_DECORATOR = "fixture"
TEST_DIR = "tests"
_TEST_PREFIX = "test_"
#: Module-level names pytest itself reads: ``pytestmark`` applies marks to every test.
PYTEST_NAMES = {"pytestmark"}
#: The mark that requests fixtures by name: ``@pytest.mark.usefixtures("no_sleep")``.
USEFIXTURES_MARK = "usefixtures"
_DUNDER = "__"
_WORD = re.compile(r"[A-Za-z_]\w*")

Definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
_DOCUMENTED = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _docstrings(tree: ast.AST) -> set[int]:
    """Find the docstrings under a node.

    Args:
        tree: Parsed source or part of it.

    Returns:
        ``id`` of every string constant that is the first statement of a module, class or
        function.
    """
    found: set[int] = set()
    for node in ast.walk(tree):
        first = node.body[0] if isinstance(node, _DOCUMENTED) and node.body else None
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            found.add(id(first.value))
    return found


def _names(tree: ast.AST, docstrings: set[int]) -> Counter[str]:
    """Count the names used under a node.

    Args:
        tree: Parsed source or part of it.
        docstrings: ``id`` of the string constants that do not count.

    Returns:
        How often each name is read, as a name, an attribute, an import or a word of a string.
    """
    seen: Counter[str] = Counter()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            seen[node.id] += 1
        elif isinstance(node, ast.Attribute):
            seen[node.attr] += 1
        elif isinstance(node, ast.alias):
            seen[node.name.rsplit(".", 1)[-1]] += 1
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            seen.update(_WORD.findall(node.value))
    return seen


def references(sources: "Iterable[str]") -> Counter[str]:
    """Count the names the given Python sources use, their docstrings left out.

    Args:
        sources: Python source texts.

    Returns:
        How often each name is read (see :func:`_names`).
    """
    seen: Counter[str] = Counter()
    for source in sources:
        tree = ast.parse(source)
        seen.update(_names(tree, _docstrings(tree)))
    return seen


def definitions(source: str) -> list[tuple[str, int, int]]:
    """List what a Python source defines and must have a user.

    Args:
        source: Python source text.

    Returns:
        ``(name, line, uses of the name inside the definition itself)`` of its functions,
        classes, methods and module-level constants, the exempt ones (see the module
        docstring) left out.
    """
    tree = ast.parse(source)
    docstrings = _docstrings(tree)
    found: list[tuple[str, int, int]] = [
        (node.name, node.lineno, _names(node, docstrings)[node.name])
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not _is_exempt(node)
    ]
    found.extend(
        (name, node.lineno, _names(node, docstrings)[name]) for name, node in _constants(tree)
    )
    return found


def _is_exempt(node: Definition) -> bool:
    """Tell whether a definition needs no caller in the product (see the module docstring).

    Args:
        node: The definition.

    Returns:
        Whether it is special, a test, a framework hook or a fixture (checked by
        :func:`unrequested_fixtures`).
    """
    if isinstance(node, ast.ClassDef):
        return node.name.startswith(_DUNDER)
    return bool(
        node.name.startswith((_DUNDER, _TEST_PREFIX))
        or node.name in FRAMEWORK_HOOKS
        or FIXTURE_DECORATOR in decorator_names(node)
    )


def _constants(tree: ast.Module) -> list[tuple[str, ast.stmt]]:
    """List a module's top-level assigned names (special and :data:`PYTEST_NAMES` left out).

    Args:
        tree: The parsed module.

    Returns:
        ``(name, assignment)`` pairs.
    """
    found: list[tuple[str, ast.stmt]] = []
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else []
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        found.extend(
            (t.id, node)
            for t in targets
            if isinstance(t, ast.Name) and not t.id.startswith(_DUNDER) and t.id not in PYTEST_NAMES
        )
    return found


def unreferenced(defining: "dict[str, str]", others: "Iterable[str]" = ()) -> list[str]:
    """Find the definitions that nothing outside themselves references.

    Args:
        defining: Python source text by its location (for the report); its references count.
        others: More sources whose references count.

    Returns:
        ``location:line name`` of every definition only referenced inside itself, if at all.
    """
    seen = references([*defining.values(), *others])
    return [
        f"{where}:{line} {name}"
        for where, source in defining.items()
        for name, line, own_uses in definitions(source)
        if seen[name] <= own_uses
    ]


def _fixtures(source: str) -> list[tuple[str, int]]:
    """List the fixtures a test source defines that a test must request.

    Args:
        source: Python source text.

    Returns:
        ``(fixture name, line)`` of each, autouse ones left out (pytest applies them unasked).
    """
    found: list[tuple[str, int]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            options = _fixture_options(decorator)
            if options is not None and not _is_true(options.get("autouse")):
                found.append((_constant_text(options.get("name")) or node.name, node.lineno))
    return found


def _fixture_options(decorator: ast.expr) -> "dict[str, ast.expr] | None":
    """Read a ``@pytest.fixture`` / ``@fixture(...)`` decorator's keyword arguments.

    Args:
        decorator: A decorator expression.

    Returns:
        Its keywords by name (empty when bare), or ``None`` if it is not a fixture decorator.
    """
    call = decorator if isinstance(decorator, ast.Call) else None
    target = call.func if call else decorator
    is_fixture = (isinstance(target, ast.Attribute) and target.attr == FIXTURE_DECORATOR) or (
        isinstance(target, ast.Name) and target.id == FIXTURE_DECORATOR
    )
    if not is_fixture:
        return None
    return {k.arg: k.value for k in call.keywords if k.arg} if call else {}


def _constant_text(node: ast.expr | None) -> str:
    """Read a string literal.

    Args:
        node: Expression (or ``None``).

    Returns:
        Its text, or ``""`` if it is not a string literal.
    """
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else ""


def _is_true(node: ast.expr | None) -> bool:
    """Tell whether an expression is the literal ``True``.

    Args:
        node: Expression (or ``None``).

    Returns:
        Whether it is ``True``.
    """
    return isinstance(node, ast.Constant) and node.value is True


def parameters(function: "ast.FunctionDef | ast.AsyncFunctionDef") -> list[str]:
    """List a function's named parameters (``*``/``**`` ones left out).

    Args:
        function: The function.

    Returns:
        Their names, in order.
    """
    arguments = function.args
    return [a.arg for a in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)]


def _requests_by_parameter(function: "ast.FunctionDef | ast.AsyncFunctionDef") -> bool:
    """Tell whether pytest resolves a function's parameters as fixtures.

    Args:
        function: The function.

    Returns:
        Whether it is a test or a fixture (a helper's parameters request nothing).
    """
    return function.name.startswith(_TEST_PREFIX) or any(
        _fixture_options(decorator) is not None for decorator in function.decorator_list
    )


def _requested_in(node: ast.AST) -> list[str]:
    """Name the fixtures one node requests.

    Args:
        node: Any node of a parsed source.

    Returns:
        The parameters of a test or a fixture, the string arguments of a ``usefixtures(...)``
        mark, or nothing.
    """
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return parameters(node) if _requests_by_parameter(node) else []
    if not isinstance(node, ast.Call):
        return []
    target = node.func
    name = target.attr if isinstance(target, ast.Attribute) else ""
    if name != USEFIXTURES_MARK:
        return []
    return [text for text in map(_constant_text, node.args) if text]


def requested(sources: "Iterable[str]") -> set[str]:
    """Collect the fixtures the given sources request, as parameters or ``usefixtures`` marks.

    Args:
        sources: Python source texts.

    Returns:
        The names.
    """
    return {
        name
        for source in sources
        for node in ast.walk(ast.parse(source))
        for name in _requested_in(node)
    }


def unrequested_fixtures(defining: "dict[str, str]") -> list[str]:
    """Find the fixtures no function of the given sources requests.

    Args:
        defining: Test source text by its location (for the report).

    Returns:
        ``location:line name`` of every fixture no parameter names.
    """
    asked = requested(defining.values())
    return [
        f"{where}:{line} {name}"
        for where, source in defining.items()
        for name, line in _fixtures(source)
        if name not in asked
    ]


def _texts(paths: "Iterable[Path]") -> dict[str, str]:
    """Read source files, keyed by their path from the repository root.

    Args:
        paths: Files to read.

    Returns:
        Text by relative path.
    """
    return {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8") for p in paths}


def test_every_product_definition_is_used_by_the_product() -> None:
    """Nothing in the package is dead, or kept alive by the tests alone."""
    product = _texts(p for p in python_files() if not is_test_path(p))
    assert unreferenced(product) == []


def test_every_test_helper_is_used() -> None:
    """Every helper of tests/ serves some test."""
    everything = _texts(python_files())
    helpers = {where: text for where, text in everything.items() if where.startswith(TEST_DIR)}
    product = [text for where, text in everything.items() if where not in helpers]
    assert unreferenced(helpers, product) == []


def test_every_fixture_is_requested() -> None:
    """Every fixture of tests/ is a parameter or a ``usefixtures`` mark somewhere (or autouse)."""
    tests = {
        where: text for where, text in _texts(python_files()).items() if where.startswith(TEST_DIR)
    }
    assert unrequested_fixtures(tests) == []


def test_planted_dead_code_is_found() -> None:
    """The rules catch what they claim to, and spare only what is exempt.

    ``handle_endtag`` is no hook here: :data:`FRAMEWORK_HOOKS` names exact methods.
    """
    product = (
        "LIMIT = 3\nUNUSED = 4\n"
        + "def used():\n    return LIMIT\n"
        + "def dead():\n    return used()\n"
        + "def hinted() -> 'Kept': ...\n"
        + "class Kept:\n    def __len__(self): return 0\n"
        + "    @property\n    def unread(self): ...\n"
        + "".join(f"    def {hook}(self): ...\n" for hook in sorted(FRAMEWORK_HOOKS))
        + 'def documented():\n    """Unlike only_in_docstring."""\n'
        + "def only_in_docstring(): ...\n"
        + "def recursive(n):\n    return recursive(n - 1)\n"
        + "class Parser(HTMLParser):\n    def handle_endtag(self, tag): ...\n"
        + "@pytest.fixture\ndef checked_as_a_fixture(): ...\n"
        + "pytestmark = pytest.mark.usefixtures('checked_as_a_fixture')\n"
    )
    # `ast.walk` order: module level first, then the classes' members.
    assert unreferenced({"m.py": product}) == [
        "m.py:5 dead",
        "m.py:7 hinted",
        "m.py:14 documented",
        "m.py:16 only_in_docstring",
        "m.py:17 recursive",
        "m.py:19 Parser",
        "m.py:11 unread",
        "m.py:20 handle_endtag",
        "m.py:2 UNUSED",
    ]


def test_planted_unused_fixture_is_found() -> None:
    """A fixture nothing requests is reported; requested, marked, renamed and autouse are not.

    A string given to another mark (``skip``) requests nothing, and neither does a helper's
    parameter named like a fixture (``lonely``).
    """
    tests = (
        "@pytest.fixture(name='marked')\ndef fixture_marked(): ...\n"
        + "@pytest.mark.usefixtures('marked')\ndef test_marked(): ...\n"
        + "pytestmark = pytest.mark.usefixtures(NOT_A_LITERAL)\n"
        + "@pytest.mark.skip('orphan')\ndef test_skipped(): ...\n"
        + "@pytest.fixture(name='port')\ndef fixture_port(): ...\n"
        + "@pytest.fixture\ndef clock(port): ...\n"
        + "@pytest.fixture(name='spare')\ndef fixture_spare(): ...\n"
        + "@fixture\ndef orphan(): ...\n"
        + "@pytest.fixture(autouse=True)\ndef isolated(): ...\n"
        + "def test_x(clock): ...\n"
        + "@pytest.fixture\ndef lonely(): ...\n"
        + "def helper(lonely): ...\n"
    )
    assert unrequested_fixtures({"t.py": tests}) == [
        "t.py:13 spare",
        "t.py:15 orphan",
        "t.py:20 lonely",
    ]
