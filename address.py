#! -*- coding: utf8 -*-

from trytond.model import ModelSQL, ModelView
from trytond.pyson import Id

__all__ = ['Address']

class Address(ModelSQL, ModelView):
    "Address"
    __name__ = 'party.address'

    @staticmethod
    def default_country():
        return Id('country', 'ar').pyson()
