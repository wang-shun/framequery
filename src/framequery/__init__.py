from __future__ import print_function, division, absolute_import

import inspect

from ._context import Context
from ._graphviz import to_dot, show


__all__ = [
    'select', 'compile', 'to_dot', 'show', 'make_context',
]


# TODO: allow to use strings for executor factory to not expose interals
def make_context(scope, strict=False, executor_factory=None):
    return Context(scope=scope, strict=strict, executor_factory=executor_factory)


def select(query, scope=None, strict=False):
    """Execute a SELECT query on the given scope.

    :param str query: the select statement as a string.

    :param Optional[Mapping[str,pandas.DataFrame]] scope: the scope as a mapping
        of table name to DataFrame. If not given the locals and globals of the
        calling scope are used to build the dictionary.

    :param bool strict: if True, create the underlying context in strict mode.
        Then, the context will perform additional steps to mimic SQL behavior.

    :returns pandas.DataFrame: the result of the query.
    """
    if scope is None:
        scope = inspect.currentframe()

    return make_context(scope=scope).select(query)


def compile(query):
    """Compile a query into a DAG of highlevel dataframe transformations.
    """
    return make_context({}).compile(query)
