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
    pyafipws_mode_cert = fields.Selection([
           ('', 'n/a'),
           ('homologacion', u'Homologación'),
           ('produccion', u'Producción'),
       ], 'Modo de certificacion',
       help=u"El objetivo de Homologación (testing), es facilitar las pruebas. Los certificados de Homologación y Producción son distintos.")

    @staticmethod
    def default_pyafipws_mode_cert():
        return ''

    @classmethod
    def __setup__(cls):
        super(Company, cls).__setup__()
        cls._error_messages.update({
            'wrong_pyafipws_mode': ('Problemas de Certificado: '
                    '"%(message)s".'),
        })

    @classmethod
    def validate(cls, companies):
        super(Company, cls).validate(companies)
        for company in companies:
            company.check_pyafipws_mode_cert()

    def check_pyafipws_mode_cert(self):
        if self.pyafipws_mode_cert == '':
            return

        auth_data = self.pyafipws_authenticate(service="wsfe", force=True)
        if auth_data['err_msg'] != None:
            self.raise_user_error('wrong_pyafipws_mode', {
                'message': auth_data['err_msg'],
            })

    def pyafipws_authenticate(self, service="wsfe", force=False):
        "Authenticate against AFIP, returns token, sign, err_msg (dict)"
        import afip_auth
        auth_data = {}
        # get the authentication credentials:
        certificate = str(self.pyafipws_certificate)
        private_key = str(self.pyafipws_private_key)
        if self.pyafipws_mode_cert == 'homologacion':
            WSAA_URL = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl"
        elif self.pyafipws_mode_cert == 'produccion':
            WSAA_URL = "https://wsaa.afip.gov.ar/ws/services/LoginCms?wsdl"
        else:
            self.raise_user_error('wrong_pyafipws_mode', {
                'message': u'El modo de certificación no es ni producción, ni homologación. Configure su Empresa',
            })

        # call the helper function to obtain the access ticket:
        auth = afip_auth.authenticate(service, certificate, private_key, wsdl=WSAA_URL, force=force)
        auth_data.update(auth)
        return auth_data
