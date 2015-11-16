from trytond.pool import Pool

from .invoice import *
from .company import *
from .pos import *
from .party import *
from .address import *

def register():
    Pool.register(
        Pos,
        PosSequence,
        Invoice,
        InvoiceExportLicense,
        Company,
        AfipWSTransaction,
        Party,
        AFIPVatCountry,
        Address,
        GetAFIPDataStart,
        module='account_invoice_ar', type_='model')
    Pool.register(
        GetAFIPData,
        module='account_invoice_ar', type_='wizard')
    Pool.register(
        InvoiceReport,
        module='account_invoice_ar', type_='report')
