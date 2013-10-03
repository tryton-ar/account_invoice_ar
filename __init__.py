from trytond.pool import Pool

from .invoice import *
from .company import *
from .journal import *

def register():
    Pool.register(
        ElectronicInvoice,
        Company,
        Journal,
        module='account_invoice_ar', type_='model')
