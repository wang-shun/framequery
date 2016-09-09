from __future__ import print_function, division, absolute_import

from collections import OrderedDict
import itertools as it
import operator

import numpy as np
import pandas as pd

from .parser import as_parsed, ColumnReference, DerivedColumn, BinaryExpression
from ._pandas_util import strip_table_name_from_columns, ensure_table_columns
from ._visitor import node_name_to_handler_name


def evaluate(q, scope=None):
    if scope is None:
        scope = {}

    q = as_parsed(q)

    evaluator = Evaluator()
    return evaluator.evaluate(q, scope)


class Evaluator(object):
    def evaluate(self, q, scope):
        assert len(q.from_clause) == 1

        # TODO: filter table
        table = lookup_table(scope, q.from_clause[0])

        if q.where_clause is not None:
            filter = self.evaluate_value(q.where_clause, table)
            table = table[filter]

        if q.group_by_clause is None:
            result = self.evaluate_direct(q.select_list, table)
            result = self.wrap_result(result)

        else:
            result = self.evaluate_grouped(q, table)

        result = strip_table_name_from_columns(result)
        return result.reset_index(drop=True)

    def evaluate_grouped(self, q, table):
        group_derived = self._groupby_as_derived(q.group_by_clause)
        group_columns = self.evaluate_direct(group_derived, table)

        grouped = table.groupby(list(group_columns.values()))

        parts = []
        for (group_idx, (key, group)) in enumerate(grouped):
            group_table = {
                k: v for (k, v) in group.items()
            }

            if len(group_columns) == 1:
                key = [key]

            group_table.update(zip(group_columns.keys(), key))

            group_result = self.evaluate_direct(q.select_list, group_table)
            group_result = self.wrap_result(group_result, index=[group_idx])
            parts.append(group_result)

        return self.concat(parts)

    def _groupby_as_derived(self, group_by):
        return [
            DerivedColumn(col, alias=col.value[-1]) for col in group_by
        ]

    def evaluate_direct(self, select_list, table):
        result = OrderedDict()
        for idx, column in enumerate(select_list):
            alias = normalize_alias(table, idx, column)
            result[alias] = self.evaluate_value(column.value, table)

        return result

    def evaluate_value(self, col, table):
        col_type = col.__class__.__name__
        handler_name = node_name_to_handler_name(col_type, prefix="evaluate_value")

        handler = getattr(self, handler_name, None)
        if handler is None:
            raise ValueError('cannot handle {} (no handler {})'.format(col, handler_name))

        return handler(col, table)

    def evaluate_value_integer(self, col, table):
        return self.as_scalar(int(col.value))

    def evaluate_value_column_reference(self, col, table):
        col_ref = normalize_col_ref(table, col)
        return table[col_ref]

    def evaluate_value_binary_expression(self, col, table):
        left = self.evaluate_value(col.left, table)
        right = self.evaluate_value(col.right, table)

        operator_map = {
            '*': operator.mul,
            '/': operator.truediv,
            '+': operator.add,
            '-': operator.sub,
            'AND': operator.and_,
            'OR': operator.or_,
            '<': operator.lt,
            '>': operator.gt,
            '<=': operator.le,
            '>=': operator.ge,
            '=': operator.eq,
            '!=': operator.ne,
        }

        try:
            op = operator_map[col.operator]

        except AttributeError:
            raise ValueError("unknown operator {}".format(col.operator))

        else:
            return op(left, right)

    def evaluate_value_general_set_function(self, col, table):
        if col.quantifier is not None:
            raise ValueError("quantifiers are currently not supported")

        value = self.evaluate_value(col.value, table)
        return self.aggregate(col.function, value)

    def concat(self, parts):
        return pd.concat(parts, axis=0)

    def wrap_result(self, result, index=None):
        return pd.DataFrame(result, index=index)

    def as_scalar(self, value):
        return [value]

    def aggregate(self, function, value):
        if function == 'SUM':
            return self.as_scalar(value.sum())

        elif function == 'AVG':
            return self.as_scalar(value.mean())

        elif function == 'MIN':
            return self.as_scalar(value.min())

        elif function == 'MAX':
            return self.as_scalar(value.max())

        else:
            raise NotImplementedError("unsupported aggregation function {}".format(function))


def lookup_table(scope, table_ref):
    table_ref = normalize_table_ref(scope, table_ref)

    if table_ref == 'DUAL':
        return None

    return scope[table_ref]


def normalize_table_ref(scope, table_ref):
    # TODO: handle schemas, etc ...
    return table_ref.table


def normalize_col_ref(table, col_ref):
    # TODO: handle schemas, etc ...
    return col_ref.value[0]


def normalize_alias(table, idx, col):
    if isinstance(col.value, ColumnReference):
        return col.value.value[-1]

    if col.alias is None:
        return '__{}'.format(idx)

    return col.alias


def as_pandas_join_condition(left_columns, right_columns, condition):
    flat_condition = flatten_join_condition(condition)

    left = []
    right = []

    for a, b in flat_condition:
        a_is_left, a = _is_left(left_columns, right_columns, a)
        b_is_left, b = _is_left(left_columns, right_columns, b)

        if a_is_left == b_is_left:
            raise ValueError("cannot join a table to itslef ({}, {})".format(a, b))

        if a_is_left:
            left.append(a)
            right.append(b)

        else:
            right.append(a)
            left.append(b)

    return left, right


def _is_left(left_columns, right_columns, ref):
    left_ref = get_col_ref(left_columns, ref)
    right_ref = get_col_ref(right_columns, ref)

    if (left_ref is None) == (right_ref is None):
        raise ValueError('col ref {} is ambigious'.format(ref))

    return (left_ref is not None), left_ref if left_ref is not None else right_ref


def get_col_ref(columns, ref):
    for col in columns:
        if all(t == u for (t, u) in zip(reversed(col), reversed(ref))):
            return col

    return None


def flatten_join_condition(condition):
    return list(_flatten_join_condition(condition))


def _flatten_join_condition(condition):
    if not isinstance(condition, BinaryExpression):
        raise ValueError("can only handle equality joins")

    if condition.operator == 'AND':
        return it.chain(
            _flatten_join_condition(condition.left),
            _flatten_join_condition(condition.right),
        )

    elif condition.operator == '=':
        if not (
            isinstance(condition.left, ColumnReference) and
            isinstance(condition.right, ColumnReference)
        ):
            raise ValueError("requires column references")

        return [(condition.left.value, condition.right.value)]

    else:
        raise ValueError("can only handle equality joins")
