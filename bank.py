# -*- coding: utf-8 -*-
# This file is part of the account_invoice_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.model import fields
from trytond.pool import PoolMeta
from trytond.pyson import Eval, If, In


class BankAccount(metaclass=PoolMeta):
    __name__ = 'bank.account'

    pyafipws_cbu = fields.Boolean('CBU del Emisor')
