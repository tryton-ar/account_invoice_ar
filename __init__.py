# This file is part of the account_invoice_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.pool import Pool
from .invoice import *
from .company import *
from .pos import *


def register():
    Pool.register(
        Pos,
        PosSequence,
        Invoice,
        InvoiceExportLicense,
        Company,
        AfipWSTransaction,
        module='account_invoice_ar', type_='model')
    Pool.register(
        InvoiceReport,
        module='account_invoice_ar', type_='report')
