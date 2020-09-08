# -*- coding: utf-8 -*-
# This file is part of the account_invoice_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import logging

from trytond.model import fields
from trytond.pool import PoolMeta
from trytond.exceptions import UserError
from trytond.i18n import gettext

logger = logging.getLogger(__name__)

__all__ = ['Company']


class Company(metaclass=PoolMeta):
    __name__ = 'company.company'

    pyafipws_certificate = fields.Text('Certificado AFIP WS',
        help='Certificado (.crt) de la empresa para webservices AFIP')
    pyafipws_private_key = fields.Text('Clave Privada AFIP WS',
        help='Clave Privada (.key) de la empresa para webservices AFIP')
    pyafipws_mode_cert = fields.Selection([
        ('', 'n/a'),
        ('homologacion', 'Homologación'),
        ('produccion', 'Producción'),
        ], 'Modo de certificacion',
        help=('El objetivo de Homologación (testing), es facilitar las '
            'pruebas. Los certificados de Homologación y Producción son '
            'distintos.'))

    @staticmethod
    def default_pyafipws_mode_cert():
        return ''

    @classmethod
    def validate(cls, companies):
        super().validate(companies)
        for company in companies:
            company.check_pyafipws_mode_cert()

    def check_pyafipws_mode_cert(self):
        if self.pyafipws_mode_cert == '':
            return

        auth_data = self.pyafipws_authenticate(service='wsfe', force=False)
        if auth_data['err_msg'] is not None:
            raise UserError(gettext(
                'account_invoice_ar.msg_wrong_pyafipws_mode',
                message=auth_data['err_msg']))

    def pyafipws_authenticate(self, service='wsfe', force=False, cache=''):
        'Authenticate against AFIP, returns token, sign, err_msg (dict)'
        from . import afip_auth
        auth_data = {}
        # get the authentication credentials:
        certificate = str(self.pyafipws_certificate)
        private_key = str(self.pyafipws_private_key)
        if self.pyafipws_mode_cert == 'homologacion':
            WSAA_URL = 'https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl'
        elif self.pyafipws_mode_cert == 'produccion':
            WSAA_URL = 'https://wsaa.afip.gov.ar/ws/services/LoginCms?wsdl'
        else:
            raise UserError(gettext(
                'account_invoice_ar.msg_wrong_pyafipws_mode',
                message=('El modo de certificación no es ni producción, ni '
                    'homologación. Configure su Empresa')))

        # call the helper function to obtain the access ticket:
        auth = afip_auth.authenticate(service, certificate, private_key,
            force=force, cache=cache, wsdl=WSAA_URL)
        auth_data.update(auth)
        if not auth_data.get('token'):
            logger.error('Error webservice WSAA: %s', auth_data.get('err_msg'))
            raise UserError(gettext(
                'account_invoice_ar.msg_wrong_pyafipws_mode',
                message=auth_data.get('err_msg'),
                ))
        return auth_data
