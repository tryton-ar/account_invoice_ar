#! -*- coding: utf8 -*-

from trytond.model import ModelView, ModelSQL, fields
from trytond.pyson import Bool, Eval

__all__ = ['Journal']

STATES={'required': Bool(Eval('pyafipws_electronic_invoice_service'))}

class Journal(ModelSQL, ModelView):
    'Journal'
    __name__ = 'account.journal'

    pyafipws_electronic_invoice_service = fields.Selection([
            ('' , ''),
            ('wsfe',   u'Mercado interno -sin detalle- RG2485 (WSFEv1)'),
#            ('wsmtxca',u'Mercado interno -con detalle- RG2904 (WSMTXCA)'),
            ('wsbfe',  u'Bono Fiscal -con detalle- RG2557 (WSMTXCA)'),
            ('wsfex',  u'Exportación -con detalle- RG2758 (WSFEXv1)'),
        ], u'AFIP Web Service',
        help= u"Habilita la facturación electrónica por webservices AFIP")

    pyafipws_invoice_type = fields.Selection([
            ('' , ''),
            ( '1',u'01-Factura A'),
            ( '2',u'02-Nota de Débito A'),
            ( '3',u'03-Nota de Crédito A'),
            ( '4',u'04-Recibos A'),
            ( '5',u'05-Nota de Venta al Contado A'),
            ( '6',u'06-Factura B'),
            ( '7',u'07-Nota de Débito B'),
            ( '8',u'08-Nota de Crédito B'),
            ( '9',u'09-Recibos B'),
            ('10',u'10-Notas de Venta al Contado B'),
            ('11',u'11-Factura C'),
            ('12',u'12-Nota de Débito C'),
            ('13',u'13-Nota de Crédito C'),
            ('15',u'Recibo C'),
            ('19',u'19-Factura E'),
            ('20',u'20-Nota de Débito E'),
            ('21',u'21-Nota de Crédito E'),
            ], 'Tipo Comprobante AFIP',
        help="Tipo de Comprobante AFIP",
        states=STATES,
        depends=['pyafipws_electronic_invoice_service'])

    pyafipws_point_of_sale = fields.Integer('Punto de Venta AFIP',
        help=u"Prefijo de emisión habilitado en AFIP",
        states=STATES,
        depends=['pyafipws_electronic_invoice_service'])

