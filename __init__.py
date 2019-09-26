# This file is part of the account_invoice_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.pool import Pool
from . import invoice
from . import company
from . import pos
from . import bank
from . import party


def register():
    Pool.register(
        pos.Pos,
        pos.PosSequence,
        invoice.Invoice,
        invoice.InvoiceExportLicense,
        invoice.CreditInvoiceStart,
        company.Company,
        invoice.AfipWSTransaction,
        bank.BankAccount,
        party.Party,
        module='account_invoice_ar', type_='model')
    Pool.register(
        invoice.CreditInvoice,
        module='account_invoice_ar', type_='wizard')
    Pool.register(
        invoice.InvoiceReport,
        module='account_invoice_ar', type_='report')
