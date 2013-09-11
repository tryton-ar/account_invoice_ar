#! -*- coding: utf8 -*-

from trytond.model import ModelSQL, Workflow

__all__ = ['ElectronicInvoice']

class ElectronicInvoice(Workflow, ModelSQL):
    'Electronic Invoice'
    __name__ = 'account.invoice'

    @classmethod
    def __setup__(cls):
        super(ElectronicInvoice, cls).__setup__()
