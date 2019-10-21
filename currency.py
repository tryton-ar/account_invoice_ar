# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import datetime
from pyafipws.wsfev1 import WSFEv1
from pyafipws.wsfexv1 import WSFEXv1
from . import afip_auth

from trytond.model import fields
from trytond.pyson import Eval, If, In
from trytond.pool import PoolMeta

__all__ = ['Currency', 'Rate']


class Currency(metaclass=PoolMeta):
    __name__ = 'currency.currency'
    afip_code = fields.Char('AFIP Code', size=3,
        help="The 3 digits AFIP currency code.")


class Rate(metaclass=PoolMeta):
    __name__ = 'currency.currency.rate'

    def get_afip_rate(self, service='wsfex'):
        '''
        get rate from afip webservice.
        '''
        pool = Pool()
        Company = pool.get('company.company')
        company_id = Transaction().context.get('company')
        if not company_id:
            logger.error('The company is not defined')
            cls.raise_user_error('company_not_defined')
        company = Company(company_id)
        # authenticate against AFIP:
        auth_data = company.pyafipws_authenticate(service=service)

        if service == 'wsfe':
            ws = WSFEv1()
            if company.pyafipws_mode_cert == 'homologacion':
                WSDL = 'https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL'
            elif company.pyafipws_mode_cert == 'produccion':
                WSDL = (
                    'https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL')
        elif service == 'wsfex':
            ws = WSFEXv1()
            if company.pyafipws_mode_cert == 'homologacion':
                WSDL = 'https://wswhomo.afip.gov.ar/wsfexv1/service.asmx?WSDL'
            elif company.pyafipws_mode_cert == 'produccion':
                WSDL = (
                    'https://servicios1.afip.gov.ar/wsfexv1/service.asmx?WSDL')
        else:
            logger.critical('AFIP ws is not yet supported! %s', service)
            cls.raise_user_error('webservice_not_supported', service)

        cache_dir = afip_auth.get_cache_dir()
        ws.LanzarExcepciones = True
        try:
            ws.Conectar(wsdl=wsdl, cache=cache_dir)
        except Exception as e:
            msg = ws.Excepcion + ' ' + str(e)
            logger.error('WSAA connecting to afip: %s' % msg)
            cls.raise_user_error('wsaa_error', msg)
        ws.Cuit = vat_number
        ws.Token = auth_data['token']
        ws.Sign = auth_data['sign']

        if not date:
            Date = pool.get('ir.date')
            today = Date.today().strftime("%Y%m%d")
        if not self.currency.afip_code:
            logger.error('AFIP code is empty %s', self.currency.code)
            cls.raise_user_error('afip_code_empty')

        self.rate = Decimal(ws.GetParamCtz('DOL'))
        self.date = datetime.datetime.strptime(ws.FchCotiz, '%Y%m%d').date()
