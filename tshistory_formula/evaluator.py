import inspect
from concurrent.futures import (
    Future
)

try:
    from functools import cache
except ImportError:
    # before python 3.9
    _CACHE = {}
    def cache(func):
        def wrapper(*a, **k):
            val = _CACHE.get(a)
            if val:
                return val
            _CACHE[a] = val = func(*a, **k)
            return val
        return wrapper


from psyl.lisp import (
    buildargs,
    let,
    quasiexpreval
)

from tshistory_formula.helper import ThreadPoolExecutor


@cache
def funcid(func):
    return hash(inspect.getsource(func))


# parallel evaluator

def pexpreval(tree, env, asyncfuncs=(), pool=None, hist=False):
    if not isinstance(tree, list):
        # we've got an atom
        # we do this very late rather than upfront
        # because the interpreter will need the original
        # symbolic expression to build names
        return quasiexpreval(tree, env)

    if tree[0] == 'let':
        tree, env = let(env, tree[1:])
        return pexpreval(tree, env, asyncfuncs, pool, hist)

    # a functional expression
    # the recursive evaluation will
    # * dereference the symbols -> functions
    # * evaluate the sub-expressions -> values
    exps = [
        pexpreval(exp, env, asyncfuncs, pool, hist)
        for exp in tree
    ]
    # since some calls are evaluated asynchronously (e.g. series) we
    # need to resolve all the future objects
    newargs = [
        arg.result() if isinstance(arg, Future) else arg
        for arg in exps[1:]
    ]
    proc = exps[0]
    posargs, kwargs = buildargs(newargs)

    # open partials to find the true operator on which we can decide
    # to go async
    if hasattr(proc, 'func'):
        func = proc.func
    else:
        func = proc

    # for autotrophic operators: prepare to pass the tree if present
    funkey = funcid(func)
    if hist and funkey in asyncfuncs:
        kwargs['__tree__'] = tree

    # an async function, e.g. series, being I/O oriented
    # can be deferred to a thread
    if funkey in asyncfuncs and pool:
        return pool.submit(proc, *posargs, **kwargs)

    # at this point, we have a function, and all the arguments
    # have been evaluated, so we do the final call
    return proc(*posargs, **kwargs)


def pevaluate(expr, env, asyncfuncs=(), concurrency=16, hist=False):
    if asyncfuncs:
        with ThreadPoolExecutor(concurrency) as pool:
            val = pexpreval(
                expr, env,
                {funcid(func) for func in asyncfuncs},
                pool,
                hist
            )
            if isinstance(val, Future):
                val = val.result()
        return val

    return pexpreval(expr, env, asyncfuncs, hist)
