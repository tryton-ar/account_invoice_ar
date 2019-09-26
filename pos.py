# -*- coding: utf-8 -*-
# This file is part of the account_invoice_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from sql import Null

from trytond import backend
from trytond.model import ModelView, ModelSQL, fields
from trytond.pyson import Eval
from trytond.pool import Pool
from trytond.transaction import Transaction

__all__ = ['Pos', 'PosSequence']
STATES = {
    'readonly': ~Eval('active', True),
}
DEPENDS = ['active']

INVOICE_TYPE_POS = [
        ('', ''),
        ('1', '01-Factura A'),
        ('2', '02-Nota de Débito A'),
        ('3', '03-Nota de Crédito A'),
        ('4', '04-Recibos A'),
        ('5', '05-Nota de Venta al Contado A'),
        ('6', '06-Factura B'),
        ('7', '07-Nota de Débito B'),
        ('8', '08-Nota de Crédito B'),
        ('9', '09-Recibos B'),
        ('10', '10-Notas de Venta al Contado B'),
        ('11', '11-Factura C'),
        ('12', '12-Nota de Débito C'),
        ('13', '13-Nota de Crédito C'),
        ('15', '15-Recibo C'),
        ('19', '19-Factura E'),
        ('20', '20-Nota de Débito E'),
        ('21', '21-Nota de Crédito E'),
        ('201', '201-Factura de Crédito Electrónica MiPyMEs A'),
        ('202', '202-Nota de Débito Electrónica MiPyMEs A'),
        ('203', '203-Nota de Crédito Electrónica MiPyMEs A'),
        ('206', '206-Factura de Crédito Electrónica MiPyMEs B'),
        ('207', '207-Nota de Débito Electrónica MiPyMEs B'),
        ('208', '208-Nota de Crédito Electrónica MiPyMEs B'),
        ('211', '211-Factura de Crédito Electrónica MiPyMEs C'),
        ('212', '212-Nota de Débito Electrónica MiPyMEs C'),
        ('213', '213-Nota de Crédito Electrónica MiPyMEs C'),
    ]


class Pos(ModelSQL, ModelView):
    'Point of Sale'
    __name__ = 'account.pos'

    company = fields.Many2One('company.company', 'Company', required=True,
        states=STATES, depends=DEPENDS)
    number = fields.Integer('Punto de Venta AFIP', required=True,
        states=STATES, depends=DEPENDS,
        help='Prefijo de emisión habilitado en AFIP')
    pos_sequences = fields.One2Many('account.pos.sequence', 'pos',
        'Point of Sale', context={'company': Eval('company', -1)},
        depends=['company', 'active'], states=STATES)
    pos_type = fields.Selection([
        ('manual', 'Manual'),
        ('electronic', 'Electronic'),
        ('fiscal_printer', 'Fiscal Printer'),
        ], 'Pos Type', required=True, states=STATES, depends=DEPENDS)
    pos_type_string = pos_type.translated('pos_type')
    pos_daily_report = fields.Boolean('Cierre diario (ZETA)', states={
            'invisible': Eval('pos_type') != 'fiscal_printer'
            },
        depends=['pos_type'])
    pyafipws_electronic_invoice_service = fields.Selection([
        ('', ''),
        ('wsfe', 'Mercado interno -sin detalle- RG2485 (WSFEv1)'),
        #('wsmtxca', 'Mercado interno -con detalle- RG2904 (WSMTXCA)'),
        ('wsbfe', 'Bono Fiscal -con detalle- RG2557 (WSMTXCA)'),
        ('wsfex', 'Exportación -con detalle- RG2758 (WSFEXv1)'),
        ], 'AFIP Web Service', depends=['pos_type', 'active'], states={
            'invisible': Eval('pos_type') != 'electronic',
            'required': Eval('pos_type') == 'electronic',
            'readonly': ~Eval('active', True),
            },
        help='Habilita la facturación electrónica por webservices AFIP')
    active = fields.Boolean('Active', select=True)

    @classmethod
    def __register__(cls, module_name):
        cursor = Transaction().connection.cursor()
        pool = Pool()
        pos_table = cls.__table__()
        company_table = pool.get('company.company').__table__()

        TableHandler = backend.get('TableHandler')
        table = TableHandler(cls, module_name)
        exist = table.column_exist('company')

        super(Pos, cls).__register__(module_name)

        # Migration from 4.2: company is required
        if not exist:
            cursor.execute(*company_table.select(company_table.id,
                where=company_table.parent == Null))
            company = cursor.fetchone()
            if company:
                cursor.execute(*pos_table.update([pos_table.company],
                    [company[0]]))

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_pos_type():
        return 'manual'

    @staticmethod
    def default_active():
        return True

    def get_rec_name(self, name):
        if self.pos_type and self.number:
            return '[%s] %s' % (str(self.number), self.pos_type_string)

    @classmethod
    def search_rec_name(cls, name, clause):
        return [('pos_type',) + tuple(clause[1:])]


class PosSequence(ModelSQL, ModelView):
    'Point of Sale Sequences'
    __name__ = 'account.pos.sequence'

    pos = fields.Many2One('account.pos', 'Point of Sale',
        ondelete='CASCADE', select=True, required=True)
    invoice_type = fields.Selection(INVOICE_TYPE_POS,
        'Tipo Comprobante AFIP', select=True, required=True,
        help='Tipo de Comprobante AFIP')
    invoice_type_string = invoice_type.translated('invoice_type')
    invoice_sequence = fields.Many2One('ir.sequence',
        'Sequence',
        domain=[
            ('code', '=', 'account.invoice'),
            ['OR',
                ('company', '=', Eval('context', {}).get('company', -1)),
                ('company', '=', None),
                ],
            ])

    @classmethod
    def __register__(cls, module_name):
        cursor = Transaction().connection.cursor()
        property_table = 'ir_property'
        pos_sequence_table = cls._table

        TableHandler = backend.get('TableHandler')
        table = TableHandler(cls, module_name)
        exist = table.column_exist('invoice_sequence')

        super(PosSequence, cls).__register__(module_name)

        # Migration from 4.2: set invoice_sequence
        if not exist and TableHandler.table_exist(property_table):
            cursor.execute('UPDATE "' + pos_sequence_table + '" '
                'SET invoice_sequence = ('
                    'SELECT split_part(value, \',\', 2) '
                    'FROM "' + property_table + '" '
                    'WHERE split_part(res, \',\', 1) = '
                        '\'account.pos.sequence\' '
                        'AND split_part(res, \',\', 2)::INTEGER = '
                        '"' + pos_sequence_table + '".id'
                    ')::INTEGER')

    def get_rec_name(self, name):
        if not self.invoice_type_string:
            return ''
        return self.invoice_type_string.split('-')[1]
