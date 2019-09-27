# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from decimal import Decimal

from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, Bool, Or
from trytond.transaction import Transaction

__all__ = ['Party']


class Party:
    __name__ = 'party.party'
    __metaclass__ = PoolMeta

    pyafipws_fce = fields.Boolean('MiPyme FCE', states={
            'readonly': ~Eval('active', True),
            }, depends=['active'])
    pyafipws_fce_amount = fields.Numeric('MiPyme FCE Amount',
            digits=(16, Eval('pyafipws_fce_amount_digits', 2)),
        states={
            'readonly': Or(~Eval('pyafipws_fce', False), ~Eval('active', True)),
            }, depends=['active', 'pyafipws_fce_amount_digits'])
    pyafipws_fce_amount_digits = fields.Function(fields.Integer(
            'Currency Digits'), 'get_pyafipws_fce_amount_digits')

    @staticmethod
    def default_pyafipws_fce_amount():
        return Decimal('0')

    def get_pyafipws_fce_amount_digits(self, name):
        pool = Pool()
        Company = pool.get('company.company')
        company_id = Transaction().context.get('company')
        if company_id:
            company = Company(company_id)
            return company.currency.digits
