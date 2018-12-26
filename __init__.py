# This file is part of the account_invoice_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.pool import Pool
from . import invoice
from . import company
from . import pos


def register():
    Pool.register(
        pos.Pos,
        pos.PosSequence,
        invoice.Invoice,
        invoice.InvoiceExportLicense,
        company.Company,
        invoice.AfipWSTransaction,
        module='account_invoice_ar', type_='model')
    Pool.register(
        invoice.InvoiceReport,
        module='account_invoice_ar', type_='report')
