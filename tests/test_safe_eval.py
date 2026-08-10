"""수식 평가기 테스트 — **탈출 시도를 적대적으로** 확인한다.

이 모듈의 존재 이유는 "계산은 되게 하되 코드는 실행되지 않게" 하는 것이다.
그러므로 "계산이 된다"는 테스트만으로는 아무것도 증명하지 못한다.
탈출 경로를 실제로 던져 막히는지 본다.

이 프로젝트는 **통과하는 보안 테스트가 잘못된 이유로 통과한** 전례가 있다
(BUILD_SPEC: `pytest.raises(Exception)`이 오타난 메서드명의 AttributeError를
'차단됨'으로 오인했다). 그래서 여기서는:
- 거부 사유를 **구체적으로** 단언한다 (아무 예외나 통과시키지 않는다)
- 허용 경로가 실제로 동작하는 **대조군**을 함께 둔다
"""

from __future__ import annotations

import math

import pytest

from registry.safe_eval import (
    MAX_EXPONENT,
    MAX_RANGE_SIZE,
    CalculationError,
    evaluate,
)

# --- 대조군: 계산이 실제로 된다 --------------------------------------------
# 이게 없으면 "전부 거부"하는 구현도 아래 보안 테스트를 전부 통과한다.


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1 + 2 * 3", 7),
        ("(120*3+45)/7", (120 * 3 + 45) / 7),
        ("2 ** 10", 1024),
        ("17 % 5", 2),
        ("17 // 5", 3),
        ("-(3 + 4)", -7),
        ("abs(-9)", 9),
        ("round(3.14159, 2)", 3.14),
        ("min(3, 1, 2)", 1),
        ("max([3, 1, 2])", 3),
        ("len(range(10))", 10),
        ("sqrt(16)", 4.0),
        ("1 < 2 < 3", True),
        ("3 if 1 > 0 else 4", 3),
    ],
)
def test_arithmetic_works(expression, expected):
    assert evaluate(expression) == expected


def test_aggregation_over_a_range_works():
    """이 도구를 만든 이유 그 자체 — 집계가 되어야 python_repl을 대체한다.

    사칙연산만 되면 Builder는 계속 python_repl을 고르고, 위험은 그대로 남는다.
    """
    result = evaluate("sum(x for x in range(1, 201) if x % 3 == 0 and x % 5 != 0)")

    assert result == sum(x for x in range(1, 201) if x % 3 == 0 and x % 5 != 0)
    assert result == 5268  # BUILD_SPEC의 단일/팀 비교에 쓰인 값


def test_list_comprehension_works():
    assert evaluate("[x * x for x in range(5)]") == [0, 1, 4, 9, 16]


def test_nested_comprehension_works():
    assert evaluate("sum(a * b for a in range(3) for b in range(3))") == 9


def test_constants_are_available():
    assert evaluate("pi") == pytest.approx(math.pi)


# --- 탈출 시도: 코드 실행 경로 ---------------------------------------------


@pytest.mark.parametrize(
    "expression",
    [
        # 속성 접근을 통한 고전적 우회 — globals를 비운 eval()이 뚫리는 경로다.
        "().__class__",
        "().__class__.__bases__[0].__subclasses__()",
        "(1).__class__.__mro__",
        "'x'.__class__",
    ],
)
def test_attribute_access_is_rejected(expression):
    """속성 접근 경로를 거부한다 — 이 경로가 존재하지 않아야 한다.

    막히는 지점은 표현식마다 다르다. `().__class__`는 Attribute 노드에서,
    `().__class__.__bases__[0].__subclasses__()`는 최외곽 Call에서(호출 대상이
    이름이 아니므로), `'x'.__class__`는 문자열 상수에서 걸린다.
    **아무 예외나 통과시키지 않도록** 알려진 거부 사유만 인정한다.
    """
    known_reasons = (
        "허용되지 않은 구문",  # Attribute 등 미허용 노드
        "함수 이름으로만 호출할 수 있다",  # 간접·속성 호출
        "숫자가 아닌 상수",  # 문자열 리터럴
    )

    with pytest.raises(CalculationError) as excinfo:
        evaluate(expression)

    message = str(excinfo.value)
    assert any(reason in message for reason in known_reasons), (
        f"예상치 못한 이유로 거부됐다 — 진짜로 막힌 것인지 확인이 필요하다: {message}"
    )


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os')",
        "eval('1+1')",
        "exec('x=1')",
        "open('secret.txt')",
        "compile('1', '<s>', 'eval')",
        "globals()",
        "locals()",
        "vars()",
        "getattr(1, 'real')",
        "input()",
    ],
)
def test_dangerous_builtins_are_rejected(expression):
    """화이트리스트에 없는 이름은 호출도 참조도 안 된다."""
    with pytest.raises(CalculationError) as excinfo:
        evaluate(expression)

    assert "호출할 수 없는 함수" in str(excinfo.value)


@pytest.mark.parametrize(
    "expression",
    [
        "import os",  # 문법상 표현식이 아니다
        "x = 1",
        "lambda: 1",
        "[x for x in range(3)][0]",  # 구독
        "f'{1}'",
        "*[1, 2]",
    ],
)
def test_non_expression_syntax_is_rejected(expression):
    with pytest.raises(CalculationError):
        evaluate(expression)


def test_string_constants_are_rejected():
    """문자열을 허용하면 이름 조작 경로가 열린다. 계산기에는 필요 없다."""
    with pytest.raises(CalculationError, match="숫자가 아닌 상수"):
        evaluate("'hello'")


def test_unknown_name_is_rejected_with_a_useful_message():
    with pytest.raises(CalculationError) as excinfo:
        evaluate("os")

    assert "알 수 없는 이름" in str(excinfo.value)
    assert "sum" in str(excinfo.value), "쓸 수 있는 함수를 알려줘야 고쳐 쓴다"


# --- 폭주 방지 --------------------------------------------------------------


def test_huge_exponent_is_rejected():
    """`2 ** 10**9`는 메모리를 다 먹고 프로세스를 멎게 한다."""
    with pytest.raises(CalculationError, match="지수가 너무 크다"):
        evaluate(f"2 ** {MAX_EXPONENT + 1}")


def test_huge_range_is_rejected():
    with pytest.raises(CalculationError, match="range 크기"):
        evaluate(f"sum(x for x in range({MAX_RANGE_SIZE + 1}))")


def test_iteration_budget_is_shared_across_nested_loops():
    """중첩 루프는 개별 range가 작아도 곱해지면 커진다.

    range 상한만 보면 `range(2000)` 두 개가 통과하지만 실제 반복은 400만 회다.
    """
    with pytest.raises(CalculationError, match="반복 횟수"):
        evaluate("sum(a * b for a in range(2000) for b in range(2000))")


def test_division_by_zero_is_a_clear_message():
    with pytest.raises(CalculationError, match="0으로 나눌 수 없다"):
        evaluate("1 / 0")


def test_result_with_too_many_items_is_rejected():
    """큰 리스트를 그대로 모델 문맥에 쏟지 않는다."""
    with pytest.raises(CalculationError, match="결과 원소가 너무 많다"):
        evaluate("[x for x in range(5000)]")


def test_empty_expression_is_rejected():
    with pytest.raises(CalculationError, match="빈 수식"):
        evaluate("   ")


# --- 도구 래퍼 --------------------------------------------------------------


def test_calculate_tool_returns_a_string_result():
    from registry.builtin import calculate

    assert calculate.invoke({"expression": "2 + 2"}) == "4"


def test_calculate_tool_reports_errors_instead_of_raising():
    """도구는 예외를 올리지 않는다 — 모델이 읽고 고쳐 쓸 수 있어야 한다."""
    from registry.builtin import calculate

    result = calculate.invoke({"expression": "__import__('os')"})

    assert result.startswith("Error:")
    assert "호출할 수 없는 함수" in result


def test_calculate_is_registered_and_offered_to_the_builder():
    """레지스트리에 올라야 스펙이 참조할 수 있고 프롬프트에도 노출된다."""
    from registry import allowed_tool_keys, tool_catalog

    assert "calculate" in allowed_tool_keys()
    assert any(info.key == "calculate" for info in tool_catalog())
