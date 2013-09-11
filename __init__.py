from trytond.pool import Pool

from .invoice import ElectronicInvoice
from .company import Company

def register():
    Pool.register(ElectronicInvoice, Company,  module='cooperative_ar', type_='model')
