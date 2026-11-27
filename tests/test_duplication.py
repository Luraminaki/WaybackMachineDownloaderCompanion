"""No duplicated code and no needless wrappers.

What a review used to catch by eye, checked on every run:

* **Pure forwarders**: a function whose whole body is ``return other(its own parameters, in
  order)`` (awaited or not, no parameters at all included) adds a name and nothing else;
  callers should call ``other``. Functions carrying one of :data:`BEHAVIOUR_DECORATORS`
  (caching, properties, fixtures), special methods and tests are exempt: they add behaviour.
* **Identical functions**: two functions with the same body, variable names aside.
* **Repeated logic**: the same :data:`RUN_STATEMENTS` statements in a row in two places, variable
  names aside, is logic to share. Runs of plain calls (``x = f(a)``, ``g(b)``, arguments that
  are names or constants) are wiring, not logic, and are allowed: entry points start alike.

Size thresholds keep one-liners and signatures out: only blocks with some substance count.
"""

import ast
from collections import defaultdict

from tests.test_conventions import (
    PROPERTY_DECORATORS,
    ROOT,
    SOURCE_DIRS,
    decorator_names,
    python_files,
)
from tests.test_unused import FIXTURE_DECORATOR, parameters

#: Decorators that make a forwarder worth its name: ``cache``/``lru_cache`` memoise,
#: ``property``/``cached_property`` turn the call into an attribute, ``fixture`` registers it
#: with pytest. Others (``staticmethod``, ``classmethod``...) add nothing: the function still
#: only forwards.
BEHAVIOUR_DECORATORS = {"cache", "lru_cache", FIXTURE_DECORATOR} | PROPERTY_DECORATORS
#: Statements in a row that make a repeated run of logic.
RUN_STATEMENTS = 3
#: Size (AST nodes) from which a run, or a function body, has substance. Counted in nodes, not
#: in ``ast.dump`` characters: from Python 3.13 the dump leaves out empty fields, so its length
#: changes with the interpreter where the node count doesn't.
MIN_RUN_SIZE = 40
MIN_BODY_SIZE = 35
_IMPLICIT = {"self", "cls"}
_TEST_PREFIX = "test_"
_DUNDER = "__"

Function = ast.FunctionDef | ast.AsyncFunctionDef


class _Renamer(ast.NodeTransformer):
    """Rename every variable and parameter by order of appearance (``v0``, ``v1``...)."""

    def __init__(self) -> None:
        """Start with no name seen."""
        self.names: dict[str, str] = {}

    def _rename(self, name: str) -> str:
        """Give a name its placeholder.

        Args:
            name: Original name.

        Returns:
            Its placeholder, the same for every use.
        """
        return self.names.setdefault(name, f"v{len(self.names)}")

    # `ast.NodeVisitor` dispatches on this exact name; `typing.override` is Python 3.12+.
    def visit_Name(self, node: ast.Name) -> ast.Name:  # pylint: disable=invalid-name
        """Rename a variable.

        Args:
            node: The name.

        Returns:
            The renamed name.
        """
        return ast.copy_location(ast.Name(id=self._rename(node.id), ctx=node.ctx), node)


def _body(function: Function) -> list[ast.stmt]:
    """Take a function's statements, its docstring left out.

    Args:
        function: The function.

    Returns:
        Its statements.
    """
    body = function.body
    first = body[0] if body else None
    is_docstring = (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    )
    return body[1:] if is_docstring else body


def _shape(statements: list[ast.stmt]) -> tuple[str, int]:
    """Describe statements independently of their variable names, and measure them.

    Args:
        statements: Statements.

    Returns:
        Their AST dump with variables renamed by order of appearance (equal for equal logic
        within one interpreter), and their size in AST nodes (the same on every interpreter).
    """
    renamer = _Renamer()
    copies = [renamer.visit(ast.parse(ast.unparse(s)).body[0]) for s in statements]
    size = sum(1 for copy in copies for _ in ast.walk(copy))
    return ast.dump(ast.Module(body=copies, type_ignores=[])), size


def _is_plain_call(node: ast.expr | None) -> bool:
    """Tell whether an expression is a call whose arguments are all names or constants.

    Args:
        node: Expression (or ``None``).

    Returns:
        Whether it is such a call, or a tuple of such calls.
    """
    if isinstance(node, ast.Tuple):
        return all(_is_plain_call(e) for e in node.elts)
    if not isinstance(node, ast.Call):
        return False
    arguments = [*node.args, *(k.value for k in node.keywords)]
    return all(isinstance(a, (ast.Name, ast.Attribute, ast.Constant)) for a in arguments)


def _is_wiring(statements: list[ast.stmt]) -> bool:
    """Tell whether statements are only plain calls, assigned or not (no logic).

    Args:
        statements: Statements.

    Returns:
        Whether every one is ``x = f(...)``, ``x, y = f(...), g(...)`` or ``f(...)``.
    """
    return all(
        isinstance(s, (ast.Assign, ast.Expr)) and _is_plain_call(s.value) for s in statements
    )


def _project() -> dict[str, str]:
    """Read the project's Python files.

    Returns:
        Source text by path from the repository root.
    """
    return {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8") for p in python_files()}


def _functions(sources: "dict[str, str]") -> list[tuple[str, Function]]:
    """List every function of the given sources, methods and nested ones included.

    Args:
        sources: Python source text by its location.

    Returns:
        ``(location, function)`` pairs.
    """
    return [
        (where, node)
        for where, source in sources.items()
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _repeated(groups: "dict[str, set[str]]") -> list[str]:
    """Keep the groups found in more than one place.

    Args:
        groups: Places by shape.

    Returns:
        One line per repeated shape, listing its places.
    """
    return [" | ".join(sorted(places)) for places in groups.values() if len(places) > 1]


def _is_exempt(function: Function) -> bool:
    """Tell whether a function may be a forwarder (it adds behaviour).

    Args:
        function: The function.

    Returns:
        Whether it carries one of :data:`BEHAVIOUR_DECORATORS`, is special or a test.
    """
    return bool(
        decorator_names(function) & BEHAVIOUR_DECORATORS
        or function.name.startswith((_DUNDER, _TEST_PREFIX))
    )


def _own_parameters(function: Function) -> list[str]:
    """List the parameters a caller passes (``self``/``cls`` and ``*``/``**`` ones left out).

    Args:
        function: The function.

    Returns:
        Their names, in order.
    """
    return [name for name in parameters(function) if name not in _IMPLICIT]


def _passed_through(call: ast.Call) -> list[str]:
    """List the names a call passes on unchanged: positional names, then ``x=x`` keywords.

    Args:
        call: The call.

    Returns:
        Those names, in order.
    """
    positional = [a.id for a in call.args if isinstance(a, ast.Name)]
    # `k.value.id`, equal to `k.arg` here, is typed `str` where `k.arg` is `str | None`.
    keywords = [
        k.value.id for k in call.keywords if isinstance(k.value, ast.Name) and k.value.id == k.arg
    ]
    return [*positional, *keywords]


def _forwarded_call(function: Function) -> ast.Call | None:
    """Find the call a function only forwards its parameters to, unchanged and in order.

    Args:
        function: The function.

    Returns:
        That call, or ``None`` if the function does anything else.
    """
    body = _body(function)
    call = body[0].value if len(body) == 1 and isinstance(body[0], ast.Return) else None
    if isinstance(call, ast.Await):
        call = call.value
    if not isinstance(call, ast.Call):
        return None
    own = _own_parameters(function)
    every_argument_passed = len(call.args) + len(call.keywords) == len(own)
    forwards = _passed_through(call) == own and every_argument_passed
    return call if forwards else None


def forwarders(sources: "dict[str, str]") -> list[str]:
    """Find the functions whose whole body forwards their own parameters, unchanged.

    Args:
        sources: Python source text by its location.

    Returns:
        ``location:line name -> call`` of each, exempt ones (see :func:`_is_exempt`) left out.
    """
    return [
        f"{where}:{function.lineno} {function.name} -> {ast.unparse(call)}"
        for where, function in _functions(sources)
        if not _is_exempt(function) and (call := _forwarded_call(function)) is not None
    ]


def shared_bodies(sources: "dict[str, str]") -> list[str]:
    """Find the functions with the same substantial body, variable names aside.

    Args:
        sources: Python source text by its location.

    Returns:
        One line per repeated body, listing its ``location:line name`` places.
    """
    groups: dict[str, set[str]] = defaultdict(set)
    for where, function in _functions(sources):
        shape, size = _shape(_body(function))
        if size >= MIN_BODY_SIZE:
            groups[shape].add(f"{where}:{function.lineno} {function.name}")
    return _repeated(groups)


def repeated_runs(sources: "dict[str, str]") -> list[str]:
    """Find the runs of :data:`RUN_STATEMENTS` statements with logic found in two places.

    Args:
        sources: Python source text by its location.

    Returns:
        One line per repeated run, listing its ``location:line function`` places.
    """
    groups: dict[str, set[str]] = defaultdict(set)
    for where, function in _functions(sources):
        body = _body(function)
        for start in range(len(body) - RUN_STATEMENTS + 1):
            run = body[start : start + RUN_STATEMENTS]
            shape, size = _shape(run)
            if size >= MIN_RUN_SIZE and not _is_wiring(run):
                groups[shape].add(f"{where}:{run[0].lineno} {function.name}")
    return _repeated(groups)


def test_no_function_only_forwards_its_arguments() -> None:
    """No function's whole body is a call passing on its own parameters, unchanged."""
    assert forwarders(_project()) == []


def test_no_two_functions_share_a_body() -> None:
    """No two functions do the same thing under different names."""
    assert shared_bodies(_project()) == []


def test_no_logic_is_repeated() -> None:
    """No run of statements with logic appears in two places (wiring aside)."""
    assert repeated_runs(_project()) == []


def test_the_scans_cover_the_project() -> None:
    """Every source directory is scanned (a renamed one would escape the checks)."""
    scanned = python_files()
    assert [d for d in SOURCE_DIRS if not any(p.is_relative_to(d) for p in scanned)] == []


#: Planted bodies for the self-test: one with logic, a run of logic, a run of wiring.
_PLANTED_LOGIC = (
    "    total = 0\n"
    "    for item in items:\n"
    "        if item.weight > limit:\n            total += item.weight * 2\n"
    "    if total > limit:\n        raise ValueError(total)\n"
    "    return {'total': total, 'limit': limit}\n"
)
_PLANTED_RUN = (
    "    found = [x for x in rows if x.ok and x.size > 3]\n"
    "    if not found:\n        raise LookupError(name)\n"
    "    best = max(found, key=lambda x: (x.size, x.name))\n"
)
_PLANTED_WIRING = (
    "    x = configure(a, 'name', 'path', 'mode', 'level', 'size', 'host')\n"
    "    y, w = start(x, a, 'port', 'retries', 'timeout'), stop(x, 'grace', 'force')\n"
    "    z = report(y, w, x, a, 'format', 'target')\n"
)
_PLANTED = {
    "m.py": "def plain(a, b):\n    return g(a, b)\n"
    + "async def awaited(a, *, b):\n    return await g(a, b=b)\n"
    + "def bare():\n    return g()\n"
    + "class C:\n"
    + "    @staticmethod\n    def static(a):\n        return g(a)\n"
    + "    def method(self, a):\n        return self.g(a)\n"
    + "    @property\n    def prop(self):\n        return self.g()\n"
    + "    def __len__(self):\n        return g()\n"
    + "@lru_cache\ndef cached(a):\n    return g(a)\n"
    + "@pytest.fixture\ndef fx():\n    return g()\n"
    + "def test_x():\n    return g()\n"
    + "def reordered(a, b):\n    return g(b, a)\n"
    + "def changed(a):\n    return g(a + 1)\n"
    + "def partial(a, b):\n    return g(a)\n"
    + "def body_one(items, limit):\n"
    + _PLANTED_LOGIC
    + "def body_two(things, cap):\n"
    + _PLANTED_LOGIC.replace("items", "things").replace(" limit", " cap")
    + "def run_one(rows, name):\n"
    + _PLANTED_RUN
    + "    return best\n"
    + "def run_two(rows, name):\n    log(name)\n"
    + _PLANTED_RUN
    + "    print(best)\n"
    + "def wiring_one(a):\n"
    + _PLANTED_WIRING
    + "    return z\n"
    + "def wiring_two(a):\n"
    + _PLANTED_WIRING
    + "    print(z)\n"
}


def test_planted_forwarders_are_found() -> None:
    """Plain, awaited, parameterless and method forwarders are caught; behaviour is spared."""
    assert forwarders(_PLANTED) == [
        "m.py:1 plain -> g(a, b)",
        "m.py:3 awaited -> g(a, b=b)",
        "m.py:5 bare -> g()",
        "m.py:9 static -> g(a)",
        "m.py:11 method -> self.g(a)",
    ]


def test_planted_shared_body_is_found() -> None:
    """Two functions differing only by their variable names are one function."""
    assert shared_bodies(_PLANTED) == ["m.py:32 body_one | m.py:40 body_two"]


def test_planted_repeated_logic_is_found() -> None:
    """A run of logic in two places is caught, a run of wiring is not."""
    assert repeated_runs(_PLANTED) == [
        "m.py:33 body_one | m.py:41 body_two",
        "m.py:34 body_one | m.py:42 body_two",
        "m.py:49 run_one | m.py:56 run_two",
    ]
