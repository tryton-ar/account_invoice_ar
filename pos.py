# -*- coding: utf-8 -*-
# This file is part of the account_invoice_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.model import ModelView, ModelSQL, fields
from trytond.pyson import Eval

__all__ = ['Pos', 'PosSequence']
STATES = {
    'readonly': ~Eval('active', True),
}
DEPENDS = ['active']

INVOICE_TYPE_POS = [
        ('', ''),
        ('1', u'01-Factura A'),
        ('2', u'02-Nota de Débito A'),
        ('3', u'03-Nota de Crédito A'),
        ('4', u'04-Recibos A'),
        ('5', u'05-Nota de Venta al Contado A'),
        ('6', u'06-Factura B'),
        ('7', u'07-Nota de Débito B'),
        ('8', u'08-Nota de Crédito B'),
        ('9', u'09-Recibos B'),
        ('10', u'10-Notas de Venta al Contado B'),
        ('11', u'11-Factura C'),
        ('12', u'12-Nota de Débito C'),
        ('13', u'13-Nota de Crédito C'),
        ('15', u'15-Recibo C'),
        ('19', u'19-Factura E'),
        ('20', u'20-Nota de Débito E'),
        ('21', u'21-Nota de Crédito E'),
        ('201', u'201-Factura de Crédito Electrónica MiPyMEs A'),
        ('202', u'202-Nota de Débito Electrónica MiPyMEs A'),
        ('203', u'203-Nota de Crédito Electrónica MiPyMEs A'),
        ('206', u'206-Factura de Crédito Electrónica MiPyMEs B'),
        ('207', u'207-Nota de Débito Electrónica MiPyMEs B'),
        ('208', u'208-Nota de Crédito Electrónica MiPyMEs B'),
        ('211', u'211-Factura de Crédito Electrónica MiPyMEs C'),
        ('212', u'212-Nota de Débito Electrónica MiPyMEs C'),
        ('213', u'213-Nota de Crédito Electrónica MiPyMEs C'),
    ]


class Pos(ModelSQL, ModelView):
    'Point of Sale'
    __name__ = 'account.pos'

    number = fields.Integer('Punto de Venta AFIP', required=True,
        states=STATES, depends=DEPENDS,
        help=u'Prefijo de emisión habilitado en AFIP')
    pos_sequences = fields.One2Many('account.pos.sequence', 'pos',
        'Point of Sale', depends=DEPENDS, states=STATES)
    pos_type = fields.Selection([
        ('manual', u'Manual'),
        ('electronic', u'Electronic'),
        ('fiscal_printer', u'Fiscal Printer'),
        ], 'Pos Type', required=True, states=STATES, depends=DEPENDS)
    pos_type_string = pos_type.translated('pos_type')
    pos_daily_report = fields.Boolean('Cierre diario (ZETA)', states={
            'invisible': Eval('pos_type') != 'fiscal_printer'
            },
        depends=['pos_type'])
    pyafipws_electronic_invoice_service = fields.Selection([
        ('', ''),
        ('wsfe', u'Mercado interno -sin detalle- RG2485 (WSFEv1)'),
        #('wsmtxca', u'Mercado interno -con detalle- RG2904 (WSMTXCA)'),
        ('wsbfe', u'Bono Fiscal -con detalle- RG2557 (WSMTXCA)'),
        ('wsfex', u'Exportación -con detalle- RG2758 (WSFEXv1)'),
        ], u'AFIP Web Service', depends=['pos_type', 'active'], states={
            'invisible': Eval('pos_type') != 'electronic',
            'required': Eval('pos_type') == 'electronic',
            'readonly': ~Eval('active', True),
            },
        help=u'Habilita la facturación electrónica por webservices AFIP')
    active = fields.Boolean('Active', select=True)

    @staticmethod
    def default_pos_type():
        return 'manual'

    @staticmethod
    def default_active():
        return True

    def get_rec_name(self, name):
        if self.pos_type and self.number:
            return '[' + str(self.number) + '] ' + self.pos_type

    @classmethod
    def search_rec_name(cls, name, clause):
        return [('pos_type',) + tuple(clause[1:])]

    #@classmethod
    #def get_name(cls, account_pos, name):
    #    res = {}
    #    for pos in cls.browse(account_pos):
    #        res[pos.id] = str(pos.number)+ ' - '+\
    #        dict(pos.fields_get(fields_names=['pos_type'])\
    #        ['pos_type']['selection'])[pos.pos_type]
    #    return res


class PosSequence(ModelSQL, ModelView):
    'Point of Sale Sequences'
    __name__ = 'account.pos.sequence'

    pos = fields.Many2One('account.pos', 'Point of Sale',
        ondelete='CASCADE', select=True, required=True)
    invoice_type = fields.Selection(INVOICE_TYPE_POS,
        'Tipo Comprobante AFIP', select=True, required=True,
        help='Tipo de Comprobante AFIP')
    invoice_type_string = invoice_type.translated('invoice_type')
    invoice_sequence = fields.Property(fields.Many2One('ir.sequence',
        'Sequence', required=True,
        domain=[('code', '=', 'account.invoice')],
        context={'code': 'account.invoice'}))

    def get_rec_name(self, name):
        if not self.invoice_type_string:
            return ''
        return self.invoice_type_string.split('-')[1]
