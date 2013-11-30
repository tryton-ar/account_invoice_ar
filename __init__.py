from trytond.pool import Pool

from .invoice import *
from .company import *
from .pos import *

def register():
    Pool.register(
        Pos,
        PosSequence,
        Invoice,
        Company,
        AfipWSTransaction,
        module='account_invoice_ar', type_='model')
