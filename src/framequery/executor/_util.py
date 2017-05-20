from __future__ import print_function, division, absolute_import

import itertools as it
from ..util._record import walk
from ..util import _monadic as m
from ..parser import ast as a


def column_match(col, internal_col):
    col_table, col = _split_table_column(col, '.')
    internal_col_table, internal_col = _split_table_column(internal_col)

    if col_table is None:
        return col == internal_col

    return internal_col_table == col_table and internal_col == col


def column_set_table(column, table):
    """Given a string column, possibly containing a table, set the table.

        >>> column_set_table('foo', 'bar')
        'bar/@/foo'

        >>> column_set_table('foo/@/bar', 'baz')
        'baz/@/bar'
    """
    return column_from_parts(table, column_get_column(column))


def column_get_table(column):
    table, _ = _split_table_column(column)
    return table


def column_get_column(column):
    """Given a string column, possibly containing a table, extract the column.

        >>> column_get_column('foo')
        'foo'

        >>> column_get_column('foo/@/bar')
        'bar'
    """
    _, column = _split_table_column(column)
    return column


def column_from_parts(table, column):
    """Given string parts, construct the full column name.

        >>> column_from_parts('foo', 'bar')
        'foo/@/bar'

    """
    if table is None:
        return column

    return '{}/@/{}'.format(table, column)


def normalize_col_ref(ref, columns, optional=False):
    ref = split_quoted_name(ref)
    ref = ref[-2:]

    if len(ref) == 2:
        table, column = ref
        return column_from_parts(table=table, column=column)

    ref_column = ref[0]

    candidates = [
        candidate
        for candidate in columns
        if column_get_column(candidate) == ref_column
    ]

    if len(candidates) == 0:
        if optional is True:
            return None

        raise ValueError("column {} not found in {}".format(ref, columns))

    if len(candidates) > 1:
        raise ValueError(
            "column {} is ambigious among {}".format(ref, columns)
        )

    return candidates[0]


def split_quoted_name(name):
    parts = []
    current = ''

    in_string = False
    after_quote = False

    for c in name:
        if after_quote:
            current += c
            after_quote = False

        elif in_string and c != '"':
            current += c

        elif c == '"':
            in_string = not in_string

        elif c == '\\':
            after_quote = True

        elif c == '.':
            parts.append(current)
            current = ''

        else:
            current += c

    parts.append(current)

    return parts


def _split_table_column(obj, sep='/@/'):
    parts = obj.split(sep, 1)

    if len(parts) == 1:
        return None, parts[0]

    return tuple(parts)


def internal_column(internal_columns):
    def internal_column_impl(obj):
        for icol in internal_columns:
            if column_match(obj, icol):
                return [obj], None, {}

        return None, obj, {}

    return m.one(internal_column_impl)


class Unique(object):
    def __hash__(self):
        return hash(id(self))


def all_unique(obj):
    return [child for child in walk(obj) if isinstance(child, Unique)]


class UniqueNameGenerator(object):
    def __init__(self, names=None, fixed=False):
        if names is None:
            names = {}

        self.names = dict(names)

        if not fixed:
            self.ids = iter(it.count())

        else:
            self.ids = None

    def get(self, obj):
        if not isinstance(obj, Unique):
            return obj

        if obj not in self.names:
            if self.ids is None:
                raise RuntimeError('cannot request unknown unique from a fixed generator')
            self.names[obj] = 'unique-{}'.format(next(self.ids))

        return self.names[obj]

    def fix(self, objs=()):
        for obj in objs:
            self.get(obj)

        return UniqueNameGenerator(self.names, fixed=True)


def eval_string_literal(value):
    # TODO: remove escapes etc..
    if value[:1] != "'":
        raise ValueError('unquoted string')

    return str(value[1:-1])


def as_pandas_join_condition(left_columns, right_columns, condition):
    flat_condition = _flatten_join_condition(condition)

    left = []
    right = []

    for aa, bb in flat_condition:
        a_is_left, aa = _is_left(left_columns, right_columns, aa)
        b_is_left, bb = _is_left(left_columns, right_columns, bb)

        if a_is_left == b_is_left:
            raise ValueError("cannot join a table to itslef ({}, {})".format(aa, bb))

        if a_is_left:
            left.append(aa)
            right.append(bb)

        else:
            right.append(aa)
            left.append(bb)

    return left, right


def _is_left(left_columns, right_columns, ref):
    left_ref = normalize_col_ref(ref, left_columns, optional=True)
    right_ref = normalize_col_ref(ref, right_columns, optional=True)

    if (left_ref is None) == (right_ref is None):
        raise ValueError('col ref {} is ambigious'.format(ref))

    return (left_ref is not None), left_ref if left_ref is not None else right_ref


def _flatten_join_condition(condition):
    if not isinstance(condition, a.BinaryOp):
        raise ValueError("can only handle equality joins")

    if condition.op == 'AND':
        return it.chain(
            _flatten_join_condition(condition.left),
            _flatten_join_condition(condition.right),
        )

    elif condition.op == '=':
        if not (
            isinstance(condition.left, a.Name) and
            isinstance(condition.right, a.Name)
        ):
            raise ValueError("requires column references")

        return [(condition.left.name, condition.right.name)]

    else:
        raise ValueError("can only handle equality joins")
