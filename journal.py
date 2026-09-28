# This file is part of the account_invoice_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.model import fields
from trytond.pool import PoolMeta
from trytond.pyson import Eval


class Journal(metaclass=PoolMeta):
    __name__ = 'account.journal'

    do_not_report = fields.Boolean('Do not report',
        states={'invisible': Eval('type') != 'expense'},
        help='Check this option if purchases from this Journal should not '
        'be included in tax reports')

    @staticmethod
    def default_do_not_report():
        return False
