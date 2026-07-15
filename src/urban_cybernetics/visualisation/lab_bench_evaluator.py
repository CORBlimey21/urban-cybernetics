"""Bounded deterministic arithmetic and finite-series evaluation for Lab Bench."""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass

from .lab_bench_contract import (
    ColumnKind,
    EvaluationRequest,
    EvaluationResult,
    LabColumn,
    LabVariable,
    TableEvaluationRequest,
    TableEvaluationResult,
)


class LabExpressionError(ValueError):
    pass


_UNIT_DEFINITIONS: dict[str, tuple[float, tuple[tuple[str, int], ...]]] = {
    "1": (1.0, ()), "": (1.0, ()), "packets": (1.0, (("packet", 1),)),
    "m": (1.0, (("length", 1),)), "km": (1000.0, (("length", 1),)),
    "s": (1.0, (("time", 1),)), "min": (60.0, (("time", 1),)), "h": (3600.0, (("time", 1),)),
    "m/s": (1.0, (("length", 1), ("time", -1))),
    "km/h": (1000.0 / 3600.0, (("length", 1), ("time", -1))),
    "packets/tick": (1.0, (("packet", 1), ("tick", -1))),
    "ticks": (1.0, (("tick", 1),)), "tick": (1.0, (("tick", 1),)),
}


@dataclass(frozen=True)
class Quantity:
    value: float
    dimensions: tuple[tuple[str, int], ...] = ()

    def _dims(self) -> dict[str, int]:
        return dict(self.dimensions)

    @staticmethod
    def from_dims(value: float, dims: dict[str, int]) -> "Quantity":
        return Quantity(value, tuple(sorted((key, exponent) for key, exponent in dims.items() if exponent)))

    def add(self, other: "Quantity", sign: int = 1) -> "Quantity":
        if self.dimensions != other.dimensions:
            raise LabExpressionError("addition/subtraction requires compatible units")
        return Quantity(self.value + sign * other.value, self.dimensions)

    def multiply(self, other: "Quantity", sign: int = 1) -> "Quantity":
        dims = self._dims()
        for key, exponent in other.dimensions:
            dims[key] = dims.get(key, 0) + sign * exponent
        value = self.value * other.value if sign == 1 else self.value / other.value
        return Quantity.from_dims(value, dims)


def _quantity(value: float | int, units: str) -> Quantity:
    try:
        scale, dimensions = _UNIT_DEFINITIONS[units]
    except KeyError as exc:
        raise LabExpressionError(f"unsupported unit: {units}") from exc
    return Quantity(float(value) * scale, dimensions)


def _display_unit(quantity: Quantity) -> str:
    for name, (scale, dimensions) in _UNIT_DEFINITIONS.items():
        if scale == 1.0 and dimensions == quantity.dimensions and name:
            return name
    if not quantity.dimensions:
        return "1"
    return " ".join(f"{name}^{power}" if power != 1 else name for name, power in quantity.dimensions)


class _Evaluator:
    def __init__(self, values: dict[str, Quantity], series: dict[str, list[Quantity]] | None = None, tick: int | None = None, out_of_range: dict[str, Quantity] | None = None) -> None:
        self.values = values
        self.series = series or {}
        self.tick = tick
        self.out_of_range = out_of_range or {}
        self.steps: list[str] = []

    def evaluate(self, expression: str) -> Quantity | bool:
        if len(expression) > 500:
            raise LabExpressionError("expression exceeds 500 characters")
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise LabExpressionError(f"invalid expression: {exc.msg}") from exc
        if sum(1 for _ in ast.walk(tree)) > 120:
            raise LabExpressionError("expression is too complex")
        return self._node(tree.body)

    def _node(self, node: ast.AST) -> Quantity | bool:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return Quantity(float(node.value))
        if isinstance(node, ast.Name):
            if node.id == "t" and self.tick is not None:
                return Quantity(float(self.tick))
            try:
                return self.values[node.id]
            except KeyError as exc:
                raise LabExpressionError(f"unknown variable: {node.id}") from exc
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = self._as_quantity(self._node(node.operand))
            return Quantity(value.value if isinstance(node.op, ast.UAdd) else -value.value, value.dimensions)
        if isinstance(node, ast.BinOp):
            left, right = self._as_quantity(self._node(node.left)), self._as_quantity(self._node(node.right))
            if isinstance(node.op, ast.Add): return left.add(right)
            if isinstance(node.op, ast.Sub): return left.add(right, -1)
            if isinstance(node.op, ast.Mult): return left.multiply(right)
            if isinstance(node.op, ast.Div):
                if right.value == 0: raise LabExpressionError("division by zero")
                return left.multiply(right, -1)
            if isinstance(node.op, ast.Pow):
                if right.dimensions or not float(right.value).is_integer() or abs(right.value) > 8:
                    raise LabExpressionError("powers require a small integer dimensionless exponent")
                exponent = int(right.value)
                return Quantity.from_dims(left.value ** exponent, {key: power * exponent for key, power in left.dimensions})
            raise LabExpressionError("unsupported arithmetic operator")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.keywords:
                raise LabExpressionError("keyword arguments are unsupported")
            name = node.func.id
            args = [self._as_quantity(self._node(arg)) for arg in node.args]
            if name in {"min", "max", "sum"}:
                if not args: raise LabExpressionError(f"{name} requires at least one argument")
                if any(item.dimensions != args[0].dimensions for item in args): raise LabExpressionError(f"{name} requires compatible units")
                value = min(item.value for item in args) if name == "min" else max(item.value for item in args) if name == "max" else sum(item.value for item in args)
                return Quantity(value, args[0].dimensions)
            if name in {"abs", "ceil", "floor"} and len(args) == 1:
                function = abs if name == "abs" else math.ceil if name == "ceil" else math.floor
                return Quantity(float(function(args[0].value)), args[0].dimensions)
            if name == "ticks" and len(args) == 2:
                if args[0].dimensions != (("time", 1),) or args[1].dimensions != (("time", 1),):
                    raise LabExpressionError("ticks(time, timestep) requires two time quantities")
                return Quantity(args[0].value / args[1].value, (("tick", 1),))
            if name == "time" and len(args) == 2:
                if args[0].dimensions not in {(), (("tick", 1),)} or args[1].dimensions != (("time", 1),):
                    raise LabExpressionError("time(ticks, timestep) requires ticks and a time quantity")
                return Quantity(args[0].value * args[1].value, (("time", 1),))
            raise LabExpressionError(f"unsupported function: {name}")
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
            left, right = self._as_quantity(self._node(node.left)), self._as_quantity(self._node(node.comparators[0]))
            if left.dimensions != right.dimensions: raise LabExpressionError("comparison requires compatible units")
            op = node.ops[0]
            if isinstance(op, ast.Eq): return left.value == right.value
            if isinstance(op, ast.NotEq): return left.value != right.value
            if isinstance(op, ast.Lt): return left.value < right.value
            if isinstance(op, ast.LtE): return left.value <= right.value
            if isinstance(op, ast.Gt): return left.value > right.value
            if isinstance(op, ast.GtE): return left.value >= right.value
            raise LabExpressionError("unsupported comparison")
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            column_id = node.value.id
            if column_id not in self.series: raise LabExpressionError(f"unknown series: {column_id}")
            index = self._as_quantity(self._node(node.slice))
            if index.dimensions or not index.value.is_integer(): raise LabExpressionError("tick references require an unambiguous integer index")
            position = int(index.value)
            values = self.series[column_id]
            if position >= len(values):
                raise LabExpressionError(f"ambiguous current/future tick reference: {column_id}[{position}]")
            if position < 0:
                if column_id not in self.out_of_range: raise LabExpressionError(f"missing initial/out-of-range convention for {column_id}[{position}]")
                return self.out_of_range[column_id]
            return values[position]
        raise LabExpressionError(f"unsupported syntax: {type(node).__name__}")

    @staticmethod
    def _as_quantity(value: Quantity | bool) -> Quantity:
        if isinstance(value, bool): raise LabExpressionError("boolean value cannot be used as a quantity")
        return value


def evaluate_expression(request: EvaluationRequest) -> EvaluationResult:
    values: dict[str, Quantity] = {}
    substitutions: list[str] = []
    for variable in request.variables:
        if not isinstance(variable.value, (int, float)):
            continue
        values[variable.variable_id] = _quantity(variable.value, variable.units)
        substitutions.append(f"{variable.variable_id}={variable.value} {variable.units}")
    evaluator = _Evaluator(values)
    result = evaluator.evaluate(request.expression)
    if isinstance(result, bool):
        return EvaluationResult(expression=request.expression, substituted_expression=", ".join(substitutions) or "no variables", value=result, units="boolean", steps=("Parsed by bounded AST evaluator.", f"Comparison result: {result}."))
    units = _display_unit(result)
    value = result.value
    if request.target_units:
        target = _quantity(1, request.target_units)
        if target.dimensions != result.dimensions: raise LabExpressionError("target unit is dimensionally incompatible")
        value = result.value / target.value
        units = request.target_units
    return EvaluationResult(expression=request.expression, substituted_expression=", ".join(substitutions) or "no variables", value=value, units=units, steps=("Parsed by bounded AST evaluator.", "Substituted declared scalar values.", f"Evaluated deterministically to {value:g} {units}."))


def _dependencies(formula: str, column_ids: set[str]) -> tuple[set[str], bool]:
    try: tree = ast.parse(formula, mode="eval")
    except SyntaxError as exc: raise LabExpressionError(f"invalid formula: {exc.msg}") from exc
    dependencies: set[str] = set()
    self_current_or_future = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id in column_ids:
            dependencies.add(node.value.id)
    return dependencies, self_current_or_future


def _dependency_order(columns: tuple[LabColumn, ...]) -> tuple[str, ...]:
    ids = {column.column_id for column in columns}
    formulas = {column.column_id: _dependencies(column.formula or "", ids)[0] - {column.column_id} for column in columns if column.kind == ColumnKind.FORMULA}
    ordered: list[str] = [column.column_id for column in columns if column.kind != ColumnKind.FORMULA]
    remaining = [column.column_id for column in columns if column.kind == ColumnKind.FORMULA]
    while remaining:
        ready = [column_id for column_id in remaining if formulas[column_id].issubset(set(ordered))]
        if not ready: raise LabExpressionError("circular table dependency detected")
        for column_id in ready:
            ordered.append(column_id); remaining.remove(column_id)
    return tuple(ordered)


def evaluate_table(request: TableEvaluationRequest) -> TableEvaluationResult:
    table = request.table
    variables = {item.variable_id: _quantity(item.value, item.units) for item in request.variables if isinstance(item.value, (int, float))}
    order = _dependency_order(table.columns)
    columns_by_id = {column.column_id: column for column in table.columns}
    size = table.tick_end - table.tick_start + 1
    series: dict[str, list[Quantity]] = {}
    for column in table.columns:
        if column.kind != ColumnKind.FORMULA:
            if len(column.values) != size: raise LabExpressionError(f"column {column.column_id} requires exactly {size} values")
            series[column.column_id] = [_quantity(value, column.units) for value in column.values]
        else:
            series[column.column_id] = []
    out_of_range = {column_id: _quantity(value, columns_by_id[column_id].units) for column_id, value in table.out_of_range_values.items() if column_id in columns_by_id}
    for row, tick in enumerate(range(table.tick_start, table.tick_end + 1)):
        for column_id in order:
            column = columns_by_id[column_id]
            if column.kind != ColumnKind.FORMULA: continue
            evaluator = _Evaluator(variables, series, tick=row, out_of_range=out_of_range)
            value = evaluator.evaluate(column.formula or "")
            if isinstance(value, bool): value = Quantity(float(value))
            expected = _quantity(1, column.units)
            if value.dimensions != expected.dimensions: raise LabExpressionError(f"formula for {column_id} is inconsistent with declared unit {column.units}")
            series[column_id].append(Quantity(value.value, expected.dimensions))
    evaluated = []
    for column in table.columns:
        unit = _quantity(1, column.units)
        values = tuple(item.value / unit.value for item in series[column.column_id])
        evaluated.append(column.model_copy(update={"values": values}))
    return TableEvaluationResult(table=table.model_copy(update={"columns": tuple(evaluated)}), dependency_order=order)
