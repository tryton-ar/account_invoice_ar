# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.model import fields
from trytond.pyson import Eval, If, In
from trytond.pool import PoolMeta

__all__ = ['BankAccount']


class BankAccount:
    __name__ = 'bank.account'
    __metaclass__ = PoolMeta

    pyafipws_cbu = fields.Boolean('CBU del Emisor', states={
            'required': If(In(Eval('party_company'),
                    Eval('owners', [])), True, False),
            }, depends=['owners', 'party_company'])
