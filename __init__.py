from trytond.pool import Pool

from .address import *
from .company import *
from .invoice import *
from .party import *
from .pos import *

def register():
    Pool.register(
        AfipWSTransaction,
        Address,
        Company,
        Invoice,
        Party,
        Pos,
        PosSequence,
        module='account_invoice_ar', type_='model')
