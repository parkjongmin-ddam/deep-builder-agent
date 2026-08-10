"""수식 평가기 — 임의 코드 실행 없이 계산만 한다.

**왜 필요한가**: `python_repl`은 임의 코드 실행이라 그 도구를 붙인 스펙은 사실상
셸을 허용한 것이다. 그런데 실제 요구의 상당수는 "숫자를 계산해줘"뿐이다.
계산만 하는 도구를 따로 두면 **대부분의 생성 에이전트가 애초에 임의 코드 실행
권한을 받지 않는다.** 위험을 없애지는 못해도 노출면을 줄인다.

**왜 `eval()`을 쓰지 않는가**: globals를 비워도 `().__class__.__bases__[0]
.__subclasses__()` 같은 속성 경로로 빠져나갈 수 있다. 널리 알려진 우회다.
여기서는 허용할 AST 노드 종류를 정하고 **직접 순회**한다 — 속성 접근(`ast.Attribute`)
노드 자체를 거부하므로 그 경로가 존재하지 않는다.

**왜 컴프리헨션까지 허용하는가**: 사칙연산만 되면 "1~200 중 3의 배수의 합" 같은
집계를 못 해서 Builder가 계속 `python_repl`을 고른다. 그러면 이 도구를 만든 목적이
사라진다. `range`와 컴프리헨션을 허용하되 크기를 묶는다.

거부하는 것: 속성 접근, 임포트, 대입, 람다, f-string, 구독(`a[0]`), 별표 인자,
화이트리스트 밖 함수 호출, 문자열·바이트 상수.
"""

from __future__ import annotations

import ast
import math
from typing import Any

# 폭주 방지 상한. 이 도구는 계산기이지 실행 환경이 아니다.
MAX_NODES = 500  # 표현식 크기
MAX_ITERATIONS = 1_000_000  # 컴프리헨션 전체 반복 횟수 합
MAX_RANGE_SIZE = 1_000_000  # range 하나의 길이
MAX_EXPONENT = 1000  # 2 ** 10**9 같은 폭탄 차단
MAX_RESULT_ITEMS = 1000  # 결과 컨테이너 길이


class CalculationError(ValueError):
    """표현식을 평가할 수 없다 (문법 오류, 금지된 구문, 상한 초과 포함)."""


def _guarded_range(*args: Any) -> range:
    """길이를 제한한 range. 없으면 `range(10**12)` 하나로 프로세스가 멎는다."""
    try:
        result = range(*args)
    except TypeError as exc:
        raise CalculationError(f"range() 인자가 잘못됐다: {exc}") from exc
    if len(result) > MAX_RANGE_SIZE:
        raise CalculationError(
            f"range 크기가 상한을 넘었다: {len(result)} > {MAX_RANGE_SIZE}"
        )
    return result


# 호출을 허용하는 함수. 여기 없는 이름은 호출도, 참조도 되지 않는다.
ALLOWED_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "len": len,
    "sorted": sorted,
    "int": int,
    "float": float,
    "range": _guarded_range,
    "sqrt": math.sqrt,
    "floor": math.floor,
    "ceil": math.ceil,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
}

# 이름으로 참조 가능한 상수.
ALLOWED_CONSTANTS: dict[str, Any] = {"pi": math.pi, "e": math.e}

_BINARY_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
}

_COMPARE_OPS = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
}


class _Evaluator:
    """AST를 직접 순회하며 평가한다. 반복 예산을 실행 전체에서 공유한다."""

    def __init__(self) -> None:
        self.iterations = 0

    def spend(self, count: int = 1) -> None:
        self.iterations += count
        if self.iterations > MAX_ITERATIONS:
            raise CalculationError(
                f"반복 횟수가 상한을 넘었다 (> {MAX_ITERATIONS}). "
                "더 작은 범위로 나눠 계산하라."
            )

    # --- 진입 ------------------------------------------------------------

    def eval(self, node: ast.AST, env: dict[str, Any]) -> Any:
        handler = getattr(self, f"_on_{type(node).__name__}", None)
        if handler is None:
            raise CalculationError(
                f"허용되지 않은 구문이다: {type(node).__name__}. 이 도구는 계산만 한다."
            )
        return handler(node, env)

    # --- 리터럴·이름 -----------------------------------------------------

    def _on_Constant(self, node: ast.Constant, env: dict[str, Any]) -> Any:
        if isinstance(node.value, (bool, int, float)):
            return node.value
        raise CalculationError(
            f"숫자가 아닌 상수는 쓸 수 없다: {node.value!r}. 이 도구는 계산만 한다."
        )

    def _on_Name(self, node: ast.Name, env: dict[str, Any]) -> Any:
        if node.id in env:
            return env[node.id]
        if node.id in ALLOWED_CONSTANTS:
            return ALLOWED_CONSTANTS[node.id]
        if node.id in ALLOWED_FUNCTIONS:
            return ALLOWED_FUNCTIONS[node.id]
        raise CalculationError(
            f"알 수 없는 이름이다: {node.id!r}. "
            f"쓸 수 있는 함수: {', '.join(sorted(ALLOWED_FUNCTIONS))}"
        )

    # --- 연산 ------------------------------------------------------------

    def _on_BinOp(self, node: ast.BinOp, env: dict[str, Any]) -> Any:
        left = self.eval(node.left, env)
        right = self.eval(node.right, env)
        self.spend()

        if isinstance(node.op, ast.Pow):
            if isinstance(right, (int, float)) and abs(right) > MAX_EXPONENT:
                raise CalculationError(f"지수가 너무 크다: {right} (상한 {MAX_EXPONENT})")
            return left**right

        op = _BINARY_OPS.get(type(node.op))
        if op is None:
            raise CalculationError(f"허용되지 않은 연산자다: {type(node.op).__name__}")
        try:
            return op(left, right)
        except ZeroDivisionError as exc:
            raise CalculationError("0으로 나눌 수 없다") from exc

    def _on_UnaryOp(self, node: ast.UnaryOp, env: dict[str, Any]) -> Any:
        value = self.eval(node.operand, env)
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.UAdd):
            return +value
        if isinstance(node.op, ast.Not):
            return not value
        raise CalculationError(f"허용되지 않은 단항 연산자다: {type(node.op).__name__}")

    def _on_BoolOp(self, node: ast.BoolOp, env: dict[str, Any]) -> Any:
        values = [self.eval(v, env) for v in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)

    def _on_Compare(self, node: ast.Compare, env: dict[str, Any]) -> Any:
        left = self.eval(node.left, env)
        for operator, comparator in zip(node.ops, node.comparators):
            right = self.eval(comparator, env)
            op = _COMPARE_OPS.get(type(operator))
            if op is None:
                raise CalculationError(
                    f"허용되지 않은 비교 연산자다: {type(operator).__name__}"
                )
            if not op(left, right):
                return False
            left = right
        return True

    def _on_IfExp(self, node: ast.IfExp, env: dict[str, Any]) -> Any:
        return (
            self.eval(node.body, env)
            if self.eval(node.test, env)
            else self.eval(node.orelse, env)
        )

    # --- 호출·컨테이너 ---------------------------------------------------

    def _on_Call(self, node: ast.Call, env: dict[str, Any]) -> Any:
        if not isinstance(node.func, ast.Name):
            raise CalculationError(
                "함수 이름으로만 호출할 수 있다 (속성 호출·간접 호출은 금지)"
            )
        if node.func.id not in ALLOWED_FUNCTIONS:
            raise CalculationError(
                f"호출할 수 없는 함수다: {node.func.id!r}. "
                f"쓸 수 있는 함수: {', '.join(sorted(ALLOWED_FUNCTIONS))}"
            )
        if node.keywords:
            raise CalculationError("키워드 인자는 지원하지 않는다")

        args = [self.eval(a, env) for a in node.args]
        self.spend()
        try:
            return ALLOWED_FUNCTIONS[node.func.id](*args)
        except CalculationError:
            raise
        except Exception as exc:  # noqa: BLE001 — 호출 실패를 사용자 메시지로 바꾼다
            raise CalculationError(f"{node.func.id}() 호출 실패: {exc}") from exc

    def _on_Tuple(self, node: ast.Tuple, env: dict[str, Any]) -> tuple:
        return tuple(self.eval(e, env) for e in node.elts)

    def _on_List(self, node: ast.List, env: dict[str, Any]) -> list:
        return [self.eval(e, env) for e in node.elts]

    def _on_Set(self, node: ast.Set, env: dict[str, Any]) -> set:
        return {self.eval(e, env) for e in node.elts}

    # --- 컴프리헨션 -------------------------------------------------------

    def _comprehend(self, node: Any, env: dict[str, Any]) -> list:
        """제너레이터 절을 순서대로 펼쳐 요소를 모은다."""
        results: list[Any] = []

        def walk(index: int, scope: dict[str, Any]) -> None:
            if index == len(node.generators):
                results.append(self.eval(node.elt, scope))
                return
            clause = node.generators[index]
            if clause.is_async:
                raise CalculationError("async 컴프리헨션은 지원하지 않는다")
            if not isinstance(clause.target, ast.Name):
                raise CalculationError("컴프리헨션 변수는 단일 이름이어야 한다")

            for item in self.eval(clause.iter, scope):
                self.spend()
                inner = {**scope, clause.target.id: item}
                if all(self.eval(cond, inner) for cond in clause.ifs):
                    walk(index + 1, inner)

        walk(0, env)
        return results

    def _on_ListComp(self, node: ast.ListComp, env: dict[str, Any]) -> list:
        return self._comprehend(node, env)

    def _on_GeneratorExp(self, node: ast.GeneratorExp, env: dict[str, Any]) -> list:
        # 제너레이터를 리스트로 되돌린다 — 지연 평가는 예산 관리를 어렵게 만든다.
        return self._comprehend(node, env)

    def _on_SetComp(self, node: ast.SetComp, env: dict[str, Any]) -> set:
        return set(self._comprehend(node, env))


def evaluate(expression: str) -> Any:
    """수식 문자열을 평가한다. 임의 코드는 실행되지 않는다.

    Raises:
        CalculationError: 문법 오류, 금지된 구문, 상한 초과.
    """
    if not expression or not expression.strip():
        raise CalculationError("빈 수식이다")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise CalculationError(f"수식을 해석할 수 없다: {exc.msg}") from exc

    node_count = sum(1 for _ in ast.walk(tree))
    if node_count > MAX_NODES:
        raise CalculationError(f"수식이 너무 복잡하다 ({node_count} 노드 > {MAX_NODES})")

    result = _Evaluator().eval(tree.body, {})

    if isinstance(result, (list, set, tuple)) and len(result) > MAX_RESULT_ITEMS:
        raise CalculationError(
            f"결과 원소가 너무 많다 ({len(result)} > {MAX_RESULT_ITEMS}). "
            "sum()·len() 등으로 집계해서 요청하라."
        )
    return result
