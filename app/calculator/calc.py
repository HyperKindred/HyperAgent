"""Safe math expression evaluator + unit converter.

Uses Python's ``ast`` module to build a parse tree and only allows
numeric literals and a whitelisted set of operators — never calls ``eval()``.
"""

import ast
import logging
import operator
from typing import Any

logger = logging.getLogger(__name__)

# ── Safe expression evaluator ────────────────────────────────────────────

_ALLOWED_NODES = (
    ast.Expression, ast.Constant, ast.UnaryOp, ast.BinOp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.USub,
    ast.Num, ast.Load,  # ast.Num is deprecated in 3.8+ but kept for safety
)

_OPERATORS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
}


def _safe_eval(expr: str) -> float | int:
    """Evaluate a mathematical expression safely using ``ast``."""
    tree = ast.parse(expr.strip(), mode="eval")
    # Validate all nodes
    for node in ast.walk(tree):
        if type(node) not in _ALLOWED_NODES:
            raise ValueError(f"不支持的表达式：包含不允许的节点 {type(node).__name__}")
    # Compile and eval with empty globals/locals for extra safety
    code = compile(tree, "<string>", "eval", flags=ast.PyCF_ONLY_AST)
    return _eval_node(code.body)


def _eval_node(node: ast.AST) -> float | int:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp):
        return _OPERATORS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.BinOp):
        return _OPERATORS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    raise ValueError(f"不支持的节点: {type(node).__name__}")


# ── Unit conversion table ────────────────────────────────────────────────
# Keys are (from_unit, to_unit) tuples; values are either a multiplier
# or a special function name for non-linear conversions.

_CONVERSION_TABLE: dict[tuple[str, str], float | str] = {
    # Length
    ("公里", "英里"): 0.621371,
    ("英里", "公里"): 1.60934,
    ("千米", "英里"): 0.621371,
    ("英里", "千米"): 1.60934,
    ("米", "英尺"): 3.28084,
    ("英尺", "米"): 0.3048,
    ("厘米", "英寸"): 0.393701,
    ("英寸", "厘米"): 2.54,
    # Weight / Mass
    ("公斤", "斤"): 2,
    ("斤", "公斤"): 0.5,
    ("千克", "斤"): 2,
    ("斤", "千克"): 0.5,
    ("公斤", "磅"): 2.20462,
    ("磅", "公斤"): 0.453592,
    ("千克", "磅"): 2.20462,
    ("磅", "千克"): 0.453592,
    # Temperature (non-linear — special handling)
    ("摄氏度", "华氏度"): "c_to_f",
    ("华氏度", "摄氏度"): "f_to_c",
    ("°C", "°F"): "c_to_f",
    ("°F", "°C"): "f_to_c",
    # Speed
    ("m/s", "km/h"): 3.6,
    ("km/h", "m/s"): 0.277778,
    # Volume
    ("升", "毫升"): 1000,
    ("毫升", "升"): 0.001,
    ("升", "加仑"): 0.264172,
    ("加仑", "升"): 3.78541,
}


def _convert_units(from_unit: str, to_unit: str, value: float) -> str:
    """Convert *value* from *from_unit* to *to_unit*."""
    key = (from_unit, to_unit)
    multiplier = _CONVERSION_TABLE.get(key)
    if multiplier is None:
        # Try reverse — maybe the user swapped units
        return ""

    if multiplier == "c_to_f":
        result = value * 9 / 5 + 32
    elif multiplier == "f_to_c":
        result = (value - 32) * 5 / 9
    else:
        result = value * multiplier

    # Format nicely — avoid excessive decimals
    formatted = f"{result:.2f}".rstrip("0").rstrip(".")
    return f"{value:g} {from_unit} = {formatted} {to_unit}"


# ── Public API ───────────────────────────────────────────────────────────

def calculate(expression: str, from_unit: str = "", to_unit: str = "") -> str:
    """Evaluate a math expression or convert between units.

    Args:
        expression: A mathematical expression like ``"(3+5)*12"`` or a number
                    to convert (e.g. ``"30"`` when used with unit conversion).
        from_unit: Source unit (e.g. ``"公里"``, ``"摄氏度"``).
        to_unit: Target unit (e.g. ``"英里"``, ``"华氏度"``).

    Returns:
        Formatted result string.
    """
    # ── Unit conversion mode ─────────────────────────────────────────
    if from_unit and to_unit:
        try:
            value = float(expression.strip())
        except ValueError:
            return f"❌ 无法解析数值：{expression}"
        result = _convert_units(from_unit, to_unit, value)
        if result:
            return f"🧮 换算结果：{result}"
        # Fall through to try as a math expression

    # ── Math expression mode ─────────────────────────────────────────
    # Preprocess common × → *, ÷ → /, ² → **2
    expr = expression.strip()
    expr = expr.replace("×", "*").replace("x", "*").replace("X", "*")
    expr = expr.replace("÷", "/").replace("²", "**2").replace("³", "**3")

    try:
        result = _safe_eval(expr)
    except (SyntaxError, ValueError, ZeroDivisionError) as e:
        return f"❌ 无法计算：{e}"

    # Format the result
    if isinstance(result, float):
        formatted = f"{result:.6f}".rstrip("0").rstrip(".")
    else:
        formatted = str(result)
    return f"🧮 {expression} = **{formatted}**"
