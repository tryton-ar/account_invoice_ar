#! -*- coding: utf8 -*-

from trytond.model import ModelView, ModelSQL, fields

__all__ = ['Company']

class Company(ModelSQL, ModelView):
    'Company'
    __name__ = 'company.company'

    pyafipws_certificate = fields.Text('Certificado AFIP WS',
        help="Certificado (.crt) de la empresa para webservices AFIP")
    pyafipws_private_key = fields.Text('Clave Privada AFIP WS',
        help="Clave Privada (.key) de la empresa para webservices AFIP")

