from sqlalchemy import select
from psyl.lisp import parse
from tshistory.tsio import TimeSerie as BaseTS

from tshistory_formula.schema import formula_schema
from tshistory_formula import interpreter


class TimeSerie(BaseTS):
    formula_map = None

    def __init__(self, namespace='tsh'):
        super().__init__(namespace)
        self.formula_schema = formula_schema(namespace)
        self.formula_schema.define()
        self.formula_map = {}

    def find_series(self, cn, stree, smap):
        if stree[0] == 'series':
            name = stree[1]
            smap[name] = self.exists(cn, name)
            return

        for arg in stree[1:]:
            if isinstance(arg, list):
                self.find_series(cn, arg, smap)

    def register_formula(self, cn, name, formula, reject_unkown=True):
        # basic syntax check
        smap = {}
        self.find_series(cn, parse(formula), smap)
        if not all(smap.values()) and reject_unkown:
            badseries = [k for k, v in smap.items() if not v]
            raise ValueError(
                f'Formula `{name}` refers to unknown series '
                f'{", ".join(badseries)}'
            )
        cn.execute(
            self.formula_schema.formula.insert().values(
                name=name,
                text=formula
            )
        )

    def isformula(self, cn, name):
        if name in self.formula_map:
            return True
        table = self.formula_schema.formula
        formula = cn.execute(
            select([table.c.text]).where(
                table.c.name==name
            )
        ).scalar()
        if formula:
            self.formula_map[name] = formula
        return bool(formula)

    def type(self, cn, name):
        if self.isformula(cn, name):
            return 'formula'

        return super().type(cn, name)

    def exists(self, cn, name):
        return super().exists(cn, name) or self.isformula(cn, name)

    def get(self, cn, name, **kw):
        if self.isformula(cn, name):
            text = self.formula_map[name]
            i = interpreter.Interpreter(cn, self, kw)
            return i.evaluate(text)

        return super().get(cn, name, **kw)
