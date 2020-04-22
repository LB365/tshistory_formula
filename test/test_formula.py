from datetime import datetime as dt, timedelta

import pandas as pd
import numpy as np
import pytest

from psyl import lisp
from tshistory.testutil import (
    assert_df,
    assert_hist,
    utcdt
)

from tshistory_formula.registry import (
    func,
    FUNCS,
    finder,
    history,
    metadata
)
from tshistory_formula.helper import (
    constant_fold
)


def test_evaluator():
    form = '(+ 2 3)'
    with pytest.raises(LookupError):
        e = lisp.evaluate(form, lisp.Env())

    env = lisp.Env({'+': lambda a, b: a + b})
    e = lisp.evaluate(form, env)
    assert e == 5

    brokenform = '(+ 2 3'
    with pytest.raises(SyntaxError):
        lisp.parse(brokenform)

    expr = ('(+ (* 8 (/ 5. 2)) 1.1)')
    tree = constant_fold(lisp.parse(expr))
    assert tree == 21.1

    expr = ('(+ (* 8 (/ 5. 2)) (series "foo"))')
    tree = constant_fold(lisp.parse(expr))
    assert tree == ['+', 20.0, ['series', 'foo']]


def test_bad_toplevel_type(engine, tsh):
    msg = 'formula `test_bad_toplevel_type` must return a `Series`, not `int`'
    with pytest.raises(TypeError, match=msg):
        tsh.register_formula(
            engine,
            'test_bad_toplevel_type',
            '(+ 2 (* 3 4))',
        )

    msg = 'formula `test_bad_toplevel_type` must return a `Series`, not `float`'
    with pytest.raises(TypeError, match=msg):
        tsh.register_formula(
            engine,
            'test_bad_toplevel_type',
            '(+ 2 (* 3 (/ 8 4)))',
        )


def test_finder(engine, tsh):
    naive = pd.Series(
        [1, 2, 3],
        index=pd.date_range(dt(2019, 1, 1), periods=3, freq='D')
    )

    tsh.update(engine, naive, 'finder', 'Babar',
               insertion_date=utcdt(2019, 1, 1))

    tsh.register_formula(
        engine,
        'test_finder',
        '(+ 2 (series "finder"))',
    )

    parsed = lisp.parse(
        tsh.formula(
            engine, 'test_finder'
        )
    )
    found = tsh.find_series(engine, parsed)
    assert found == {
        'finder': parsed[2]
    }

    tsh.register_formula(
        engine,
        'test_finder_primary_plus_formula',
        '(add (series "test_finder") (series "finder"))',
    )
    parsed = lisp.parse(
        tsh.formula(
            engine, 'test_finder_primary_plus_formula'
        )
    )
    found = tsh.find_series(engine, parsed)
    assert found == {
        'finder': parsed[2],
        'test_finder': parsed[1]
    }


def test_metadata(engine, tsh):
    naive = pd.Series(
        [1, 2, 3],
        index=pd.date_range(dt(2019, 1, 1), periods=3, freq='D')
    )

    tsh.update(engine, naive, 'metadata_naive', 'Babar',
               insertion_date=utcdt(2019, 1, 1))

    tsh.register_formula(
        engine,
        'test_meta',
        '(+ 2 (series "metadata_naive"))',
    )

    assert tsh.metadata(engine, 'test_meta') == {
        'index_dtype': '<M8[ns]',
        'index_type': 'datetime64[ns]',
        'tzaware': False,
        'value_dtype': '<f8',
        'value_type': 'float64'
    }

    aware = pd.Series(
        [1, 2, 3],
        index=pd.date_range(utcdt(2019, 1, 1), periods=3, freq='D')
    )
    tsh.update(engine, aware, 'metadata_tzaware', 'Babar',
               insertion_date=utcdt(2019, 1, 1))


    with pytest.raises(ValueError) as err:
        tsh.register_formula(
            engine,
            'test_meta_mismatch',
            '(add (series "test_meta") (series "metadata_tzaware"))',
        )
    assert err.value.args[0] == (
        "Formula `metadata_tzaware` has tzaware vs tznaive series:`"
        "('test_meta', ('add, 'series)):tznaive`,"
        "`('metadata_tzaware', ('add, 'series)):tzaware`"
    )

    tsh.register_formula(
        engine,
        'test_meta_primary_plus_formula',
        '(add (series "test_meta") (series "metadata_naive"))',
    )
    meta = tsh.metadata(engine, 'test_meta_primary_plus_formula')
    assert meta == {
        'index_dtype': '<M8[ns]',
        'index_type': 'datetime64[ns]',
        'tzaware': False,
        'value_dtype': '<f8',
        'value_type': 'float64'
    }


def test_series_options(engine, tsh):
    test = pd.Series(
        [1, 2, 3],
        index=pd.date_range(dt(2019, 1, 1), periods=3, freq='D')
    )
    tsh.update(engine, test, 'options-a', 'Babar')
    tsh.update(engine, test, 'options-b', 'Babar')
    tsh.register_formula(
        engine,
        'test_series_option',
        '(add (series "options-a") (series "options-b"))',
    )

    ts = tsh.get(engine, 'test_series_option')
    assert ts.options == {}


def test_override_primary(engine, tsh):
    test = pd.Series(
        [1, 2, 3],
        index=pd.date_range(dt(2019, 1, 1), periods=3, freq='D')
    )
    tsh.update(engine, test, 'a-primary', 'Babar')

    with pytest.raises(TypeError) as err:
        tsh.register_formula(
            engine,
            'a-primary',
            '(+ 3 (series "a-primary"))'
        )

    assert err.value.args[0] == (
        'primary series `a-primary` cannot be overriden by a formula'
    )


def test_normalization(engine, tsh):
    test = pd.Series(
        [1, 2, 3],
        index=pd.date_range(dt(2019, 1, 1), periods=3, freq='D')
    )
    tsh.update(engine, test, 'normalize', 'Babar')
    tsh.register_formula(
        engine,
        'test_normalization',
        '( add ( series "normalize") ( series  "normalize" )\n  ) ',
    )

    form = tsh.formula(engine, 'test_normalization')
    assert form == '(add (series "normalize") (series "normalize"))'


def test_base_api(engine, tsh):
    tsh.register_formula(engine, 'test_plus_two', '(+ 2 (series "test"))', False)
    tsh.register_formula(engine, 'test_three_plus', '(+ 3 (series "test"))', False)

    with pytest.raises(AssertionError):
        tsh.register_formula(engine, 'test_plus_two', '(+ 2 (series "test"))',
                             reject_unknown=False,
                             update=False)
    # accept an update
    tsh.register_formula(engine, 'test_plus_two', '(+ 2 (series "test"))',
                         reject_unknown=False,
                         update=True)

    test = pd.Series(
        [1, 2, 3],
        index=pd.date_range(dt(2019, 1, 1), periods=3, freq='D')
    )

    tsh.update(engine, test, 'test', 'Babar',
               insertion_date=utcdt(2019, 1, 1))

    twomore = tsh.get(engine, 'test_plus_two')
    assert_df("""
2019-01-01    3.0
2019-01-02    4.0
2019-01-03    5.0
""", twomore)

    nope = tsh.get(engine, 'test_plus_two', revision_date=utcdt(2018, 1, 1))
    assert len(nope) == 0

    evenmore = tsh.get(engine, 'test_three_plus')
    assert_df("""
2019-01-01    4.0
2019-01-02    5.0
2019-01-03    6.0
""", evenmore)

    tsh.register_formula(engine, 'test_product_a', '(* 1.5 (series "test"))', False)
    tsh.register_formula(engine, 'test_product_b', '(* 2 (series "test"))', False)

    series = tsh.list_series(engine)
    assert series['test'] == 'primary'
    assert series['test_product_a'] == 'formula'

    plus = tsh.get(engine, 'test_product_a')
    assert_df("""
2019-01-01    1.5
2019-01-02    3.0
2019-01-03    4.5
""", plus)

    plus = tsh.get(engine, 'test_product_b')
    assert_df("""
2019-01-01    2.0
2019-01-02    4.0
2019-01-03    6.0
""", plus)

    m = tsh.metadata(engine, 'test_product_a')
    assert m == {
        'index_dtype': '<M8[ns]',
        'index_type': 'datetime64[ns]',
        'tzaware': False,
        'value_dtype': '<f8',
        'value_type': 'float64'
    }

    tsh.update_metadata(engine, 'test_product_a', {'topic': 'spot price'})
    m = tsh.metadata(engine, 'test_product_a')
    assert m == {
        'index_dtype': '<M8[ns]',
        'index_type': 'datetime64[ns]',
        'topic': 'spot price',
        'tzaware': False,
        'value_dtype': '<f8',
        'value_type': 'float64'
    }

    tsh.update_metadata(
        engine, 'test_product_a', {
            'topic': 'Spot Price',
            'unit': '€'
        }
    )
    m = tsh.metadata(engine, 'test_product_a')
    assert m == {
        'index_dtype': '<M8[ns]',
        'index_type': 'datetime64[ns]',
        'topic': 'Spot Price',
        'tzaware': False,
        'unit': '€',
        'value_dtype': '<f8',
        'value_type': 'float64'
    }

    tsh.delete(engine, 'test_plus_two')
    assert not tsh.exists(engine, 'test_plus_two')


def test_boolean_support(engine, tsh):
    @func('op-with-boolean-kw')
    def customseries(zeroes: bool=False) -> pd.Series:
        return pd.Series(
            np.array([1.0, 2.0, 3.0]) * zeroes,
            index=pd.date_range(dt(2019, 1, 1), periods=3, freq='D')
        )

    tsh.register_formula(
        engine,
        'no-zeroes',
        '(op-with-boolean-kw)'
    )
    tsh.register_formula(
        engine,
        'zeroes',
        '(op-with-boolean-kw #:zeroes #t)'
    )

    ts1 = tsh.get(engine, 'no-zeroes')
    assert_df("""
2019-01-01    0.0
2019-01-02    0.0
2019-01-03    0.0
""", ts1)

    ts2 = tsh.get(engine, 'zeroes')
    assert_df("""
2019-01-01    1.0
2019-01-02    2.0
2019-01-03    3.0
""", ts2)

    FUNCS.pop('op-with-boolean-kw')


def test_scalar_ops(engine, tsh):
    x = pd.Series(
        [1, 2, 3],
        index=pd.date_range(dt(2020, 1, 1), periods=3, freq='D')
    )
    tsh.update(engine, x, 'scalar-ops', 'Babar')

    tsh.register_formula(
        engine,
        'scalar-formula',
        '(+ (+ (/ 20 (* 2 5)) 1) (series "scalar-ops"))',
    )
    ts = tsh.get(engine, 'scalar-formula')
    assert_df("""
2020-01-01    4.0
2020-01-02    5.0
2020-01-03    6.0
""", ts)


def test_options(engine, tsh):
    @func('dummy')
    def dummy(option: int=None) -> pd.Series:
        series = pd.Series(
            [1, 2, 3],
            index=pd.date_range(dt(2019, 1, 1), periods=3, freq='D')
        )
        series.options = {'option': option}
        return series

    tsh.register_formula(
        engine,
        'test_options',
        '(* 3 (dummy #:option 42))',
        False
    )

    ts = tsh.get(engine, 'test_options')
    assert_df("""
2019-01-01    3
2019-01-02    6
2019-01-03    9
""", ts)
    assert ts.options == {'option': 42}

    FUNCS.pop('dummy')


def test_error(engine, tsh):
    with pytest.raises(SyntaxError):
        tsh.register_formula(
            engine,
            'test_error',
            '(clip (series "a")'
        )

    with pytest.raises(ValueError) as err:
        tsh.register_formula(
            engine,
            'test_error',
            '(priority (series "NOPE1") (series "NOPE2" #:prune 1))'
        )
    assert err.value.args[0] == (
        'Formula `test_error` refers to '
        'unknown series `NOPE1`, `NOPE2`'
    )


def test_history(engine, tsh):
    tsh.register_formula(
        engine,
        'h-addition',
        '(add (series "ha") (series "hb"))',
        False
    )

    for day in (1, 2, 3):
        idate = utcdt(2019, 1, day)
        for name in 'ab':
            ts = pd.Series(
                [day] * 3,
                index=pd.date_range(dt(2018, 1, 1), periods=3, freq='D')
            )
            tsh.update(engine, ts, 'h' + name, 'Babar',
                       insertion_date=idate)

    h = tsh.history(engine, 'h-addition')
    assert_hist("""
insertion_date             value_date
2019-01-01 00:00:00+00:00  2018-01-01    2.0
                           2018-01-02    2.0
                           2018-01-03    2.0
2019-01-02 00:00:00+00:00  2018-01-01    4.0
                           2018-01-02    4.0
                           2018-01-03    4.0
2019-01-03 00:00:00+00:00  2018-01-01    6.0
                           2018-01-02    6.0
                           2018-01-03    6.0
""", h)

    dates = tsh.insertion_dates(engine, 'h-addition')
    assert dates == [
        (1, pd.Timestamp('2019-01-01 00:00:00+0000', tz='UTC')),
        (2, pd.Timestamp('2019-01-02 00:00:00+0000', tz='UTC')),
        (3, pd.Timestamp('2019-01-03 00:00:00+0000', tz='UTC'))
    ]

    h = tsh.history(
        engine, 'h-addition',
        from_insertion_date=utcdt(2019, 1, 2),
        to_insertion_date=utcdt(2019, 1, 2),
        from_value_date=dt(2018, 1, 2),
        to_value_date=dt(2018, 1, 2)
    )
    assert_hist("""
insertion_date             value_date
2019-01-02 00:00:00+00:00  2018-01-02    4.0
""", h)

    # let's add a priority
    tsh.register_formula(
        engine,
        'h-priority',
        '(priority (series "hz") (series "h-addition"))',
        False
    )
    for day in (1, 2, 3):
        idate = utcdt(2019, 1, day)
        ts = pd.Series(
            [41 + day] * 3,
            index=pd.date_range(dt(2018, 1, 3), periods=3, freq='D')
        )
        tsh.update(engine, ts, 'hz', 'Babar',
                   insertion_date=idate)

    h = tsh.history(engine, 'h-priority')
    assert_hist("""
insertion_date             value_date
2019-01-01 00:00:00+00:00  2018-01-01     2.0
                           2018-01-02     2.0
                           2018-01-03    42.0
                           2018-01-04    42.0
                           2018-01-05    42.0
2019-01-02 00:00:00+00:00  2018-01-01     4.0
                           2018-01-02     4.0
                           2018-01-03    43.0
                           2018-01-04    43.0
                           2018-01-05    43.0
2019-01-03 00:00:00+00:00  2018-01-01     6.0
                           2018-01-02     6.0
                           2018-01-03    44.0
                           2018-01-04    44.0
                           2018-01-05    44.0
""", h)


def test_staircase(engine, tsh):
    tsh.register_formula(
        engine,
        's-addition',
        '(add (series "sa") (series "sb"))',
        False
    )

    for day in (1, 2, 3, 4, 5):
        idate = utcdt(2018, 1, day)
        for name in 'ab':
            ts = pd.Series(
                [day / 2.] * 5,
                index=pd.date_range(dt(2018, 1, day), periods=5, freq='D')
            )
            tsh.update(engine, ts, 's' + name, 'Babar',
                       insertion_date=idate)

    ts = tsh.staircase(engine, 's-addition', delta=pd.Timedelta(hours=12))
    assert_df("""
2018-01-02    1.0
2018-01-03    2.0
2018-01-04    3.0
2018-01-05    4.0
2018-01-06    5.0
2018-01-07    5.0
2018-01-08    5.0
2018-01-09    5.0
""", ts)

    # this is not allowed in the staircase fast-path
    # hence we will take the slow path
    @func('identity')
    def identity(series: pd.Series) -> pd.Series:
        return series

    tsh.register_formula(
        engine,
        'slow-down',
        '(identity (series "sa"))',
        False
    )

    tsh.register_formula(
        engine,
        's-addition-not-fast',
        '(add (series "slow-down") (series "sb"))',
        False
    )
    ts = tsh.staircase(
        engine,
        's-addition-not-fast',
        delta=pd.Timedelta(hours=12)
    )
    assert_df("""
2018-01-02    1.0
2018-01-03    2.0
2018-01-04    3.0
2018-01-05    4.0
2018-01-06    5.0
2018-01-07    5.0
2018-01-08    5.0
2018-01-09    5.0
""", ts)

    # cleanup
    FUNCS.pop('identity')


def test_new_func(engine, tsh):

    @func('identity')
    def identity(series: pd.Series) -> pd.Series:
        return series

    tsh.register_formula(
        engine,
        'identity',
        '(identity (series "id-a"))',
        False
    )

    ts = pd.Series(
        [1, 2, 3],
        index=pd.date_range(dt(2019, 1, 1), periods=3, freq='D')
    )
    tsh.update(engine, ts, 'id-a', 'Babar')

    ts = tsh.get(engine, 'identity')
    assert_df("""
2019-01-01    1.0
2019-01-02    2.0
2019-01-03    3.0
""", ts)

    # cleanup
    FUNCS.pop('identity')


def test_ifunc(engine, tsh):

    @func('shifted')
    def shifted(__interpreter__, name: str, days: int=0) -> pd.Series:
        args = __interpreter__.getargs.copy()
        fromdate = args.get('from_value_date')
        todate = args.get('to_value_date')
        if fromdate:
            args['from_value_date'] = fromdate + timedelta(days=days)
        if todate:
            args['to_value_date'] = todate + timedelta(days=days)

        return __interpreter__.get(name, args)

    @metadata('shifted')
    def shifted_metadata(cn, tsh, stree):
        return {
            stree[1]: tsh.metadata(cn, stree[1])
        }

    @finder('shifted')
    def shifted_finder(cn, tsh, stree):
        return {
            stree[1]: stree
        }

    tsh.register_formula(
        engine,
        'shifting',
        '(+ 0 (shifted "shiftme" #:days -1))',
        False
    )

    ts = pd.Series(
        [1, 2, 3, 4, 5],
        index=pd.date_range(dt(2019, 1, 1), periods=5, freq='D')
    )
    tsh.update(
        engine, ts, 'shiftme', 'Babar',
        insertion_date=utcdt(2019, 1, 1)
    )

    ts = tsh.get(engine, 'shifting')
    assert_df("""
2019-01-01    1.0
2019-01-02    2.0
2019-01-03    3.0
2019-01-04    4.0
2019-01-05    5.0
""", ts)

    ts = tsh.get(
        engine, 'shifting',
        from_value_date=dt(2019, 1, 3),
        to_value_date=dt(2019, 1, 4)
    )
    assert_df("""
2019-01-02    2.0
2019-01-03    3.0
""", ts)

    # now, history

    ts = pd.Series(
        [1, 2, 3, 4, 5],
        index=pd.date_range(dt(2019, 1, 2), periods=5, freq='D')
    )
    tsh.update(
        engine, ts, 'shiftme', 'Babar',
        insertion_date=utcdt(2019, 1, 2)

    )
    hist = tsh.history(
        engine, 'shifting'
    )
    assert_hist("""
insertion_date             value_date
2019-01-01 00:00:00+00:00  2019-01-01    1.0
                           2019-01-02    2.0
                           2019-01-03    3.0
                           2019-01-04    4.0
                           2019-01-05    5.0
2019-01-02 00:00:00+00:00  2019-01-01    1.0
                           2019-01-02    1.0
                           2019-01-03    2.0
                           2019-01-04    3.0
                           2019-01-05    4.0
                           2019-01-06    5.0
""", hist)

    hist = tsh.history(
        engine, 'shifting',
        from_value_date=dt(2019, 1, 3),
        to_value_date=dt(2019, 1, 4)
    )
    assert_hist("""
insertion_date             value_date
2019-01-01 00:00:00+00:00  2019-01-03    3.0
                           2019-01-04    4.0
2019-01-02 00:00:00+00:00  2019-01-03    2.0
                           2019-01-04    3.0
""", hist)

    # cleanup
    FUNCS.pop('shifted')


def test_newop_expansion(engine, tsh):
    @func('combine')
    def shifted(__interpreter__, name1: str, name2: str) -> pd.Series:
        args = __interpreter__.getargs.copy()
        return (
            __interpreter__.get(name1, args) +
            __interpreter__.get(name2, args)
        )

    @metadata('combine')
    def combine_metadata(cn, tsh, stree):
        return {
            stree[1]: tsh.metadata(cn, stree[1])
        }

    ts = pd.Series(
        [1, 2, 3],
        index=pd.date_range(dt(2019, 1, 1), periods=3, freq='D')
    )
    tsh.update(engine, ts, 'base-comb', 'Babar')

    tsh.register_formula(
        engine,
        'comb-a',
        '(add (series "base-comb") (series "base-comb"))'
    )
    tsh.register_formula(
        engine,
        'comb-b',
        '(priority (series "base-comb") (series "base-comb"))'
    )

    tsh.register_formula(
        engine,
        'combinator',
        '(combine "comb-a" "comb-b")',
        False
    )

    exp = tsh.expanded_formula(engine, 'combinator')
    assert exp == '(combine "comb-a" "comb-b")'


def test_formula_refers_to_nothing(engine, tsh):
    tsh.register_formula(
        engine,
        'i-cant-work',
        '(+ 1 (series "lol"))',
        False
    )

    with pytest.raises(ValueError) as err:
        tsh.get(engine, 'i-cant-work')
    assert err.value.args[0] == 'No such series `lol`'


def test_rename(engine, tsh):
    ts = pd.Series(
        [1, 2, 3],
        index=pd.date_range(dt(2019, 1, 1), periods=3, freq='D')
    )
    tsh.update(engine, ts, 'rename-a', 'Babar')

    tsh.register_formula(
        engine,
        'survive-renaming',
        '(+ 1 (series "rename-a" #:fill 0))'
    )
    tsh.register_formula(
        engine,
        'survive-renaming-2',
        '(add (series "survive-renaming") (series "rename-a" #:fill 0))'
    )

    ts = tsh.get(engine, 'survive-renaming')
    assert_df("""
2019-01-01    2.0
2019-01-02    3.0
2019-01-03    4.0
""", ts)

    ts = tsh.get(engine, 'survive-renaming-2')
    assert_df("""
2019-01-01    3.0
2019-01-02    5.0
2019-01-03    7.0
""", ts)

    with engine.begin() as cn:
        tsh.rename(cn, 'rename-a', 'a-renamed')

    ts = tsh.get(engine, 'survive-renaming')
    assert_df("""
2019-01-01    2.0
2019-01-02    3.0
2019-01-03    4.0
""", ts)

    ts = tsh.get(engine, 'survive-renaming-2')
    assert_df("""
2019-01-01    3.0
2019-01-02    5.0
2019-01-03    7.0
""", ts)

    with engine.begin() as cn:
        with pytest.raises(ValueError) as err:
            tsh.rename(cn, 'a-renamed', 'survive-renaming')

    assert err.value.args[0] == 'new name is already referenced by `survive-renaming-2`'

    # rename a formula !
    with engine.begin() as cn:
        tsh.rename(cn, 'survive-renaming', 'survived')
    assert tsh.formula(
        engine, 'survive-renaming-2'
    ) == '(add (series "survived") (series "a-renamed" #:fill 0))'


def test_unknown_operator(engine, tsh):
    with pytest.raises(ValueError) as err:
        tsh.register_formula(
            engine,
            'nope',
            '(bogus-1 (bogus-2))',
            False
        )

    assert err.value.args[0] == (
        'Formula `nope` refers to unknown operators `bogus-1`, `bogus-2`'
    )


def test_custom_metadata(engine, tsh):
    @func('customseries')
    def customseries() -> pd.Series:
        return pd.Series(
            [1.0, 2.0, 3.0],
            index=pd.date_range(dt(2019, 1, 1), periods=3, freq='D')
        )

    @metadata('customseries')
    def customseries_metadata(_cn, _tsh, tree):
        return {
            tree[0]: {
                'index_type': 'datetime64[ns]',
                'index_dtype': '|M8[ns]',
                'tzaware': False,
                'value_type': 'float64',
                'value_dtype': '<f8'
            }
        }

    tsh.register_formula(
        engine,
        'custom',
        '(+ 3 (customseries))',
        False
    )

    meta = tsh.metadata(engine, 'custom')
    assert meta == {
        'index_type': 'datetime64[ns]',
        'index_dtype': '|M8[ns]',
        'tzaware': False,
        'value_type': 'float64',
        'value_dtype': '<f8'
    }

    # cleanup
    FUNCS.pop('customseries')


def test_custom_history(engine, tsh):
    @func('made-up-series')
    def madeup(base: int, coeff: float=1.) -> pd.Series:
        return pd.Series(
            np.array([base, base + 1, base + 2]) * coeff,
            index=pd.date_range(dt(2019, 1, 1), periods=3, freq='D')
        )

    @metadata('made-up-series')
    def madeup_metadata(_cn, _tsh, tree):
        return {
            tree[0]: {
                'index_type': 'datetime64[ns]',
                'index_dtype': '|M8[ns]',
                'tzaware': False,
                'value_type': 'float64',
                'value_dtype': '<f8'
            }
        }

    @history('made-up-series')
    def madeup_history(__interpreter__, base, coeff):
        hist = {}
        for i in (1, 2, 3):
            hist[pd.Timestamp(f'2020-1-{i}', tz='utc')] = pd.Series(
                np.array([base, base + 1, base + 2]) * coeff,
                index=pd.date_range(dt(2019, 1, i), periods=3, freq='D')
            )
        return hist

    tsh.register_formula(
        engine,
        'made-up',
        '(+ 3 (add (made-up-series 1 #:coeff 2.) (made-up-series 2 #:coeff .5)))',
        False
    )
    assert_df("""
2019-01-01     6.0
2019-01-02     8.5
2019-01-03    11.0
""", tsh.get(engine, 'made-up'))

    hist = tsh.history(engine, 'made-up')
    assert_hist("""
insertion_date             value_date
2020-01-01 00:00:00+00:00  2019-01-01     6.0
                           2019-01-02     8.5
                           2019-01-03    11.0
2020-01-02 00:00:00+00:00  2019-01-01     6.0
                           2019-01-02     8.5
                           2019-01-03    11.0
2020-01-03 00:00:00+00:00  2019-01-01     6.0
                           2019-01-02     8.5
                           2019-01-03    11.0
""", hist)


def test_expanded(engine, tsh):
    @func('customseries')
    def customseries() -> pd.Series:
        return pd.Series(
            [1.0, 2.0, 3.0],
            index=pd.date_range(dt(2019, 1, 1), periods=3, freq='D')
        )

    @metadata('customseries')
    def customseries_metadata(_cn, _tsh, tree):
        return {
            tree[0]: {
                'tzaware': True,
                'index_type': 'datetime64[ns, UTC]',
                'value_type': 'float64',
                'index_dtype': '|M8[ns]',
                'value_dtype': '<f8'
            }
        }

    base = pd.Series(
        [1, 2, 3],
        index=pd.date_range(utcdt(2019, 1, 1), periods=3, freq='D')
    )
    tsh.update(engine, base, 'exp-a', 'Babar')
    tsh.update(engine, base, 'exp-b', 'Celeste')

    tsh.register_formula(
        engine,
        'expandmebase1',
        '(+ 3 (priority (series "exp-a") (customseries)))',
        False
    )
    tsh.register_formula(
        engine,
        'expandmebase2',
        '(priority (series "exp-a") (series "exp-b"))',
        False
    )
    tsh.register_formula(
        engine,
        'expandme',
        '(add (series "expandmebase1") (series "exp-b") (series "expandmebase2"))',
        False
    )

    exp = tsh.expanded_formula(engine, 'expandme')
    assert exp == (
        '(add '
        '(+ 3 (priority (series "exp-a") (customseries))) '
        '(series "exp-b") '
        '(priority (series "exp-a") (series "exp-b")))'
    )
