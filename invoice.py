# -*- coding: utf-8 -*-
# This file is part of the account_invoice_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from pyafipws.wsfev1 import WSFEv1
from pyafipws.wsfexv1 import WSFEXv1
from pyafipws.pyi25 import PyI25
from io import BytesIO

from collections import defaultdict
import logging
from decimal import Decimal
from datetime import date
from calendar import monthrange
from unicodedata import normalize

from trytond.model import ModelSQL, Workflow, fields, ModelView
from trytond import backend
from trytond.tools import cursor_dict
from trytond.pyson import Eval, And, If
from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta
from trytond.modules.account_invoice_ar.pos import INVOICE_TYPE_POS
from . import afip_auth

logger = logging.getLogger(__name__)

__all__ = ['Invoice', 'AfipWSTransaction', 'InvoiceExportLicense',
    'InvoiceReport']

_STATES = {
    'readonly': Eval('state') != 'draft',
    }
_DEPENDS = ['state']

_REF_NUMBERS_STATES = _STATES.copy()
_REF_NUMBERS_STATES.update({
    'invisible': ~Eval('pos_pos_daily_report', False),
    'required': Eval('pos_pos_daily_report', False),
})

_BILLING_STATES = _STATES.copy()
_BILLING_STATES.update({
    'required': Eval('pyafipws_concept').in_(['2', '3']),
    })

_POS_STATES = _STATES.copy()
_POS_STATES.update({
    'required': And(Eval('type') == 'out', Eval('state') != 'draft'),
    'invisible': Eval('type') == 'in',
    })

IVA_AFIP_CODE = defaultdict(lambda: 0)
IVA_AFIP_CODE.update({
    Decimal('0'): 3,
    Decimal('0.105'): 4,
    Decimal('0.21'): 5,
    Decimal('0.27'): 6,
    })

INVOICE_TYPE_AFIP_CODE = {
        ('out', False, 'A'): ('1', '01-Factura A'),
        ('out', False, 'B'): ('6', '06-Factura B'),
        ('out', False, 'C'): ('11', '11-Factura C'),
        ('out', False, 'E'): ('19', '19-Factura E'),
        ('out', True, 'A'): ('3', '03-Nota de Cŕedito A'),
        ('out', True, 'B'): ('8', '08-Nota de Cŕedito B'),
        ('out', True, 'C'): ('13', '08-Nota de Cŕedito C'),
        ('out', True, 'E'): ('21', '08-Nota de Cŕedito E'),
        }
INVOICE_CREDIT_AFIP_CODE = {
        '1': ('3', '03-Nota de Crédito A'),
        '2': ('3', '03-Nota de Crédito A'),
        '3': ('2', '02-Nota de Débito A'),
        '6': ('8', '08-Nota de Crédito B'),
        '7': ('8', '08-Nota de Crédito B'),
        '8': ('7', '07-Nota de Débito B'),
        '11': ('13', '13-Nota de Crédito C'),
        '12': ('13', '13-Nota de Crédito C'),
        '13': ('12', '12-Nota de Débito C'),
        '19': ('21', '21-Nota de Crédito E'),
        '20': ('21', '21-Nota de Crédito E'),
        '21': ('20', '20-Nota de Débito E'),
        '27': ('48','48-Nota de Credito Liquidacion CLASE A'),
        '28': ('43','43-Nota de Credito Liquidacion CLASE B'),
        '29': ('44','44-Nota de Credito Liquidacion CLASE C'),
        '51':  ('53','53-NotaS de Credito M'),
        '81': ('112','112-Tique Nota de Credito A'),
        '82': ('113','113-Tique Nota de Credito B'),
        '83': ('110','110-Tique Nota de Credito'),
        '111': ('114','114-Tique Nota de Credito C'),
        '118': ('119','119-Tique Nota de Credito M'),
        '201': ('203','203-Nota de Credito Electronica MiPyMEs (FCE) A'),
        '206': ('208','208-Nota de Credito Electronica MiPyMEs (FCE) B'),
        '211': ('213','213- Nota de Credito Electronica MiPyMEs (FCE) C'),
        }

INCOTERMS = [
        ('', ''),
        ('EXW', 'EX WORKS'),
        ('FCA', 'FREE CARRIER'),
        ('FAS', 'FREE ALONGSIDE SHIP'),
        ('FOB', 'FREE ON BOARD'),
        ('CFR', 'COST AND FREIGHT'),
        ('CIF', 'COST, INSURANCE AND FREIGHT'),
        ('CPT', 'CARRIAGE PAID TO'),
        ('CIP', 'CARRIAGE AND INSURANCE PAID TO'),
        ('DAF', 'DELIVERED AT FRONTIER'),
        ('DES', 'DELIVERED EX SHIP'),
        ('DEQ', 'DELIVERED EX QUAY'),
        ('DDU', 'DELIVERED DUTY UNPAID'),
        ('DAT', 'Delivered At Terminal'),
        ('DAP', 'Delivered At Place'),
        ('DDP', 'Delivered Duty Paid'),
        ]

TIPO_COMPROBANTE = [
    ('', ''),
    ('001', 'FACTURAS A'),
    ('002', 'NOTAS DE DEBITO A'),
    ('003', 'NOTAS DE CREDITO A'),
    ('004', 'RECIBOS A'),
    ('005', 'NOTAS DE VENTA AL CONTADO A'),
    ('006', 'FACTURAS B'),
    ('007', 'NOTAS DE DEBITO B'),
    ('008', 'NOTAS DE CREDITO B'),
    ('009', 'RECIBOS B'),
    ('010', 'NOTAS DE VENTA AL CONTADO B'),
    ('011', 'FACTURAS C'),
    ('012', 'NOTAS DE DEBITO C'),
    ('013', 'NOTAS DE CREDITO C'),
    ('015', 'RECIBOS C'),
    ('016', 'NOTAS DE VENTA AL CONTADO C'),
    ('017', 'LIQUIDACION DE SERVICIOS PUBLICOS CLASE A'),
    ('018', 'LIQUIDACION DE SERVICIOS PUBLICOS CLASE B'),
    ('019', 'FACTURAS DE EXPORTACION'),
    ('020', 'NOTAS DE DEBITO POR OPERACIONES CON EL EXTERIOR'),
    ('021', 'NOTAS DE CREDITO POR OPERACIONES CON EL EXTERIOR'),
    ('022', 'FACTURAS - PERMISO EXPORTACION SIMPLIFICADO - DTO. 855/97'),
    ('023', 'COMPROBANTES A DE COMPRA PRIMARIA SECTOR PESQUERO MARITIMO'),
    ('024', 'COMPROBANTES A DE CONSIGNACION PRIMARIA SECTOR PESQUERO '
        'MARITIMO'),
    ('025', 'COMPROBANTES B DE COMPRA PRIMARIA SECTOR PESQUERO MARITIMO'),
    ('026', 'COMPROBANTES B DE CONSIGNACION PRIMARIA SECTOR PESQUERO '
        'MARITIMO'),
    ('027', 'LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE A'),
    ('028', 'LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE B'),
    ('029', 'LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE C'),
    ('030', 'COMPROBANTES DE COMPRA DE BIENES USADOS'),
    ('031', 'MANDATO - CONSIGNACION'),
    ('032', 'COMPROBANTES PARA RECICLAR MATERIALES'),
    ('033', 'LIQUIDACION PRIMARIA DE GRANOS'),
    ('034', 'COMPROBANTES A DEL APARTADO A INCISO F RG N.1415'),
    ('035', 'COMPROBANTES B DEL ANEXO I, APARTADO A, INC. F), RG N. 1415'),
    ('036', 'COMPROBANTES C DEL Anexo I, Apartado A, INC.F), R.G. N° 1415'),
    ('037', 'NOTAS DE DEBITO O DOCUMENTO EQUIVALENTE CON LA R.G. N° 1415'),
    ('038', 'NOTAS DE CREDITO O DOCUMENTO EQUIVALENTE CON LA R.G. N° 1415'),
    ('039', 'OTROS COMPROBANTES A QUE CUMPLEN CON LA R G  1415'),
    ('040', 'OTROS COMPROBANTES B QUE CUMPLAN CON LA R.G. N° 1415'),
    ('041', 'OTROS COMPROBANTES C QUE CUMPLAN CON LA R.G. N° 1415'),
    ('043', 'NOTA DE CREDITO LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE B'),
    ('044', 'NOTA DE CREDITO LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE C'),
    ('045', 'NOTA DE DEBITO LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE A'),
    ('046', 'NOTA DE DEBITO LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE B'),
    ('047', 'NOTA DE DEBITO LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE C'),
    ('048', 'NOTA DE CREDITO LIQUIDACION UNICA COMERCIAL IMPOSITIVA CLASE A'),
    ('049', 'COMPROBANTES DE COMPRA DE BIENES NO REGISTRABLES A CONSUMIDORES '
        'FINALES'),
    ('050', 'RECIBO FACTURA A  REGIMEN DE FACTURA DE CREDITO'),
    ('051', 'FACTURAS M'),
    ('052', 'NOTAS DE DEBITO M'),
    ('053', 'NOTAS DE CREDITO M'),
    ('054', 'RECIBOS M'),
    ('055', 'NOTAS DE VENTA AL CONTADO M'),
    ('056', 'COMPROBANTES M DEL ANEXO I  APARTADO A  INC F) R.G. N° 1415'),
    ('057', 'OTROS COMPROBANTES M QUE CUMPLAN CON LA R.G. N° 1415'),
    ('058', 'CUENTAS DE VENTA Y LIQUIDO PRODUCTO M'),
    ('059', 'LIQUIDACIONES M'),
    ('060', 'CUENTAS DE VENTA Y LIQUIDO PRODUCTO A'),
    ('061', 'CUENTAS DE VENTA Y LIQUIDO PRODUCTO B'),
    ('063', 'LIQUIDACIONES A'),
    ('064', 'LIQUIDACIONES B'),
    ('066', 'DESPACHO DE IMPORTACION'),
    ('068', 'LIQUIDACION C'),
    ('070', 'RECIBOS FACTURA DE CREDITO'),
    ('080', 'INFORME DIARIO DE CIERRE (ZETA) - CONTROLADORES FISCALES'),
    ('081', 'TIQUE FACTURA A'),
    ('082', 'TIQUE FACTURA B'),
    ('083', 'TIQUE'),
    ('088', 'REMITO ELECTRONICO'),
    ('089', 'RESUMEN DE DATOS'),
    ('090', 'OTROS COMPROBANTES - DOCUMENTOS EXCEPTUADOS - NOTAS DE CREDITO'),
    ('091', 'REMITOS R'),
    ('099', 'OTROS COMPROBANTES QUE NO CUMPLEN O ESTÁN EXCEPTUADOS DE LA '
        'R.G. 1415 Y SUS MODIF'),
    ('110', 'TIQUE NOTA DE CREDITO'),
    ('111', 'TIQUE FACTURA C'),
    ('112', 'TIQUE NOTA DE CREDITO A'),
    ('113', 'TIQUE NOTA DE CREDITO B'),
    ('114', 'TIQUE NOTA DE CREDITO C'),
    ('115', 'TIQUE NOTA DE DEBITO A'),
    ('116', 'TIQUE NOTA DE DEBITO B'),
    ('117', 'TIQUE NOTA DE DEBITO C'),
    ('118', 'TIQUE FACTURA M'),
    ('119', 'TIQUE NOTA DE CREDITO M'),
    ('120', 'TIQUE NOTA DE DEBITO M'),
    ('331', 'LIQUIDACION SECUNDARIA DE GRANOS'),
    ('332', 'CERTIFICACION ELECTRONICA (GRANOS)'),
    ]


class AfipWSTransaction(ModelSQL, ModelView):
    'AFIP WS Transaction'
    __name__ = 'account_invoice_ar.afip_transaction'

    invoice = fields.Many2One('account.invoice', 'Invoice',
        ondelete='CASCADE', select=True, required=True)
    pyafipws_result = fields.Selection([
        ('', 'n/a'),
        ('A', 'Aceptado'),
        ('R', 'Rechazado'),
        ('O', 'Observado'),
        ], 'Resultado', readonly=True,
        help='Resultado procesamiento de la Solicitud, devuelto por AFIP')
    pyafipws_message = fields.Text('Mensaje', readonly=True,
        help='Mensaje de error u observación, devuelto por AFIP')
    pyafipws_xml_request = fields.Text('Requerimiento XML', readonly=True,
        help='Mensaje XML enviado a AFIP (depuración)')
    pyafipws_xml_response = fields.Text('Respuesta XML', readonly=True,
        help='Mensaje XML recibido de AFIP (depuración)')


class Invoice(metaclass=PoolMeta):
    __name__ = 'account.invoice'

    pos = fields.Many2One('account.pos', 'Point of Sale',
        domain=[('company', '=', Eval('company'))],
        states=_POS_STATES, depends=_DEPENDS + ['company'])
    invoice_type = fields.Many2One('account.pos.sequence', 'Comprobante',
        domain=[('pos', '=', Eval('pos')),
            ('invoice_type', 'in',
                If(Eval('total_amount', -1) >= 0,
                    ['1', '2', '4', '5', '6', '7', '9', '11', '12', '15', '19'],
                    ['3', '8', '13', '21']),
                )],
        states=_POS_STATES, depends=_DEPENDS + ['pos','invoice_type',
            'total_amount'])
    invoice_type_tree = fields.Function(fields.Selection(INVOICE_TYPE_POS,
            'Tipo comprobante'), 'get_comprobante',
        searcher='search_comprobante')
    pyafipws_concept = fields.Selection([
        ('1', '1-Productos'),
        ('2', '2-Servicios'),
        ('3', '3-Productos y Servicios (mercado interno)'),
        ('4', '4-Otros (exportación)'),
        ('', ''),
        ], 'Concepto', select=True, depends=['state'], states={
            'readonly': Eval('state') != 'draft',
            'required': Eval('pos.pos_type') == 'electronic',
            })
    pyafipws_billing_start_date = fields.Date('Fecha Desde',
        states=_BILLING_STATES, depends=_DEPENDS,
        help='Seleccionar fecha de fin de servicios - Sólo servicios')
    pyafipws_billing_end_date = fields.Date('Fecha Hasta',
        states=_BILLING_STATES, depends=_DEPENDS,
        help='Seleccionar fecha de inicio de servicios - Sólo servicios')
    pyafipws_cae = fields.Char('CAE', size=14, readonly=True,
        help='Código de Autorización Electrónico, devuelto por AFIP')
    pyafipws_cae_due_date = fields.Date('Vencimiento CAE', readonly=True,
        help='Fecha tope para verificar CAE, devuelto por AFIP')
    pyafipws_barcode = fields.Char('Codigo de Barras', size=41,
        help='Código de barras para usar en la impresión', readonly=True,)
    pyafipws_number = fields.Char('Número', size=13, readonly=True,
        help='Número de factura informado a la AFIP')
    transactions = fields.One2Many('account_invoice_ar.afip_transaction',
        'invoice', 'Transacciones', readonly=True)
    tipo_comprobante = fields.Selection(TIPO_COMPROBANTE, 'Comprobante',
        select=True, depends=['state', 'type'], states={
            'invisible': Eval('type') == 'out',
            'readonly': Eval('state') != 'draft',
            })
    tipo_comprobante_string = tipo_comprobante.translated('tipo_comprobante')
    pyafipws_incoterms = fields.Selection(INCOTERMS, 'Incoterms')
    pyafipws_licenses = fields.One2Many('account.invoice.export.license',
        'invoice', 'Export Licenses')
    ref_pos_number = fields.Function(fields.Char('POS Number', size=5, states={
        'required': And(Eval('type') == 'in', Eval('state') != 'draft'),
        'invisible': Eval('type') == 'out',
        'readonly': Eval('state') != 'draft',
        }), 'get_ref_subfield', setter='set_ref_subfield')
    ref_voucher_number = fields.Function(fields.Char('Voucher Number', size=8,
        states={
            'required': And(Eval('type') == 'in', Eval('state') != 'draft'),
            'invisible': Eval('type') == 'out',
            'readonly': Eval('state') != 'draft',
        }), 'get_ref_subfield', setter='set_ref_subfield')
    pos_pos_daily_report = fields.Function(
        fields.Boolean('account.pos', "POS Daily Report"),
        'on_change_with_pos_pos_daily_report')
    ref_number_from = fields.Char('From number', size=13, states=_REF_NUMBERS_STATES,
        depends=['pos_pos_daily_report', 'state'])
    ref_number_to = fields.Char('To number', size=13, states=_REF_NUMBERS_STATES,
        depends=['pos_pos_daily_report', 'state'])
    annulled = fields.Function(fields.Boolean('Annulled', states={
        'invisible': Eval('total_amount', -1) <= 0,
        }, depends=['total_amount']), 'get_annulled')

    @classmethod
    def __setup__(cls):
        super(Invoice, cls).__setup__()
        cls.reference.states.update({
            'readonly': Eval('type') == 'in',
        })
        cls.number.depends = ['pos_pos_daily_report', 'state']
        cls.number.states.update({
            'invisible': And(Eval('pos_pos_daily_report', False) == True,
            Eval('state', 'draft').in_(['draft', 'validated', 'cancel']))
        })
        cls._error_messages.update({
            'missing_pyafipws_concept':
                'The "concept" is required if pos type is electronic',
            'missing_pyafipws_billing_date':
                'Debe establecer los valores "Fecha desde" y "Fecha hasta" '
                'en el Diario, correspondientes al servicio que se está '
                'facturando',
            'invalid_invoice_number':
                'El número de la factura (%d), no coincide con el que espera '
                'la AFIP (%d). Modifique la secuencia del diario',
            'not_cae':
                'No fue posible obtener el CAE de la factura "%(invoice)s" '
                'para la entidad "%(party)s". Mensaje: "%(msg)s"',
            'invalid_journal':
                'Este diario (%s) no tiene establecido los datos necesaios '
                'para facturar electrónicamente',
            'missing_sequence':
                'No existe una secuencia para facturas del tipo: %s',
            'too_many_sequences':
                'Existe mas de una secuencia para facturas del tipo: %s',
            'missing_company_iva_condition': 'The iva condition on company '
                '"%(company)s" is missing.',
            'missing_party_iva_condition': 'The iva condition on party '
                '"%(party)s" is missing.',
            'not_invoice_type':
                'El campo "Tipo de factura" en "Factura" es requerido.',
            'miss_tax_identifier':
                'La empresa no tiene configurado el identificador impositivo',
            'missing_currency_rate':
                'Debe configurar la cotización de la moneda.',
            'missing_pyafipws_incoterms':
                'Debe establecer el valor de Incoterms si desea realizar '
                'un tipo de "Factura E".',
            'reference_unique':
                'El numero de factura ya ha sido ingresado en el sistema.',
            'tax_without_group':
                'El impuesto (%s) debe tener un grupo asignado '
                '(iibb, municipal, iva).',
            'in_invoice_validate_failed':
                'Los campos "Referencia" y "Comprobante" son requeridos.',
            'rejected_invoices':
                'There was a problem at invoices IDs "%(invoices)s".\n'
                'Check out error messages: "%(msg)s"',
            'webservice_unknown':
                'AFIP web service is unknown',
            'webservice_not_supported':
                'AFIP webservice %s is not yet supported!',
            'company_not_defined':
                'The company is not defined',
            'wsaa_error':
                'There was a problem to connect webservice WSAA: (%s)',
            'error_caesolicitarx':
                'Error CAESolicitarX: (%s)',
            'invalid_ref_number':
                'The value "%(ref_value)s" is not a number.',
            'invalid_ref_from_to':
                '"From number" must be smaller than "To number"'
            })

    @classmethod
    def __register__(cls, module_name):
        super(Invoice, cls).__register__(module_name)
        cursor = Transaction().connection.cursor()
        cursor.execute('UPDATE account_invoice SET tipo_comprobante = \'001\' '
            'WHERE tipo_comprobante = \'fca\';')
        cursor.execute('UPDATE account_invoice SET tipo_comprobante = \'006\' '
            'WHERE tipo_comprobante = \'fcb\';')
        cursor.execute('UPDATE account_invoice SET tipo_comprobante = \'011\' '
            'WHERE tipo_comprobante = \'fcc\';')
        cursor.execute('UPDATE account_invoice SET tipo_comprobante = \'081\' '
            'WHERE tipo_comprobante = \'tka\';')
        cursor.execute('UPDATE account_invoice SET tipo_comprobante = \'082\' '
            'WHERE tipo_comprobante = \'tkb\';')
        cursor.execute('UPDATE account_invoice SET tipo_comprobante = \'111\' '
            'WHERE tipo_comprobante = \'tkc\';')

    @fields.depends('pos')
    def on_change_with_pos_pos_daily_report(self, name=None):
        if self.pos:
            return self.pos.pos_daily_report

    @classmethod
    def order_invoice_type_tree(cls, tables):
        table, _ = tables[None]
        return [table.invoice_type]

    @classmethod
    def search_comprobante(cls, name, clause):
        return [
            ('invoice_type.invoice_type',) + tuple(clause[1:]),
            ]

    @classmethod
    def copy(cls, invoices, default=None):
        if default is None:
            default = {}
        else:
            default = default.copy()
        default['transactions'] = None
        default['pyafipws_cae'] = None
        default['pyafipws_cae_due_date'] = None
        default['pyafipws_barcode'] = None
        default['pyafipws_number'] = None
        default['pyafipws_number'] = None
        default['pos'] = None
        default['invoice_type'] = None
        default['ref_pos_number'] = None
        default['ref_voucher_number'] = None
        default['reference'] = None
        default['tipo_comprobante'] = None
        return super(Invoice, cls).copy(invoices, default=default)

    @classmethod
    def validate(cls, invoices):
        super(Invoice, cls).validate(invoices)
        for invoice in invoices:
            invoice.check_unique_daily_report()

    @classmethod
    def get_annulled(cls, invoices, name):
        lines = defaultdict(list)
        invoices = [i for i in invoices if i.state == 'paid']
        for invoice in invoices:
            for line in invoice.lines_to_pay:
                if line.reconciliation:
                    lines[invoice.id] = len(line.search([
                        ('reconciliation', '=', line.reconciliation),
                        ('id', '!=', line.id),
                        ('origin.total_amount', '<', 0, 'account.invoice'),
                    ])) > 0
                    break
        return lines

    def check_unique_daily_report(self):
        if (self.type == 'out' and self.pos
        and self.pos.pos_daily_report == True):
            if int(self.ref_number_from) > int(self.ref_number_to):
                self.raise_user_error('invalid_ref_from_to')
            else:
                invoices = self.search([
                    ('id', '!=', self.id),
                    ('type', '=', self.type),
                    ('pos', '=', self.pos),
                    ('invoice_type', '=', self.invoice_type),
                    ('state', '!=', 'cancel'),
                    ])
                for invoice in invoices:
                    if (invoice.ref_number_to != None and invoice.ref_number_from != None
                    and (int(self.ref_number_from) >= int(invoice.ref_number_from)
                    and int(self.ref_number_from) <= int(invoice.ref_number_to))
                    or (int(self.ref_number_to) <= int(invoice.ref_number_to)
                    and int(self.ref_number_to) >= int(invoice.ref_number_from))):
                        self.raise_user_error('reference_unique')

    @classmethod
    def view_attributes(cls):
        return super(Invoice, cls).view_attributes() + [
            ('/form/notebook/page[@id="electronic_invoice"]', 'states', {
                    'invisible': Eval('type') == 'in',
                    }),
            ('/form/notebook/page[@id="electronic_invoice_incoterms"]',
                'states', {
                    'invisible': Eval('type') == 'in',
                    }),
            ('/tree/field[@name="tipo_comprobante"]', 'tree_invisible',
                    Eval('type') == 'out'),
            ('/tree/field[@name="invoice_type_tree"]', 'tree_invisible',
                    Eval('type') == 'in'),
            ]

    def get_comprobante(self, name):
        if self.type == 'out' and self.invoice_type:
            return self.invoice_type.invoice_type
        return None

    def get_ref_subfield(self, name):
        if self.type == 'in' and self.reference and '-' in self.reference:
            if name == 'ref_pos_number':
                return self.reference.split('-')[0].lstrip('0')
            elif name == 'ref_voucher_number':
                return self.reference.split('-')[1].lstrip('0')
        return None

    @classmethod
    def set_ref_subfield(cls, invoices, name, value):
        if value and not value.isdigit():
            cls.raise_user_error('invalid_ref_number', {
                    'ref_value': value,
                })
        reference = None
        for invoice in invoices:
            if invoice.type == 'in':
                if name == 'ref_pos_number':
                    reference = '%05d-%08d' % (int(value or 0), int(invoice.ref_voucher_number or 0))
                elif name == 'ref_voucher_number':
                    reference = '%05d-%08d' % (int(invoice.ref_pos_number or 0), int(value or 0))
                invoice.reference = reference
        cls.save(invoices)

    @classmethod
    @ModelView.button
    @Workflow.transition('validated')
    def validate_invoice(cls, invoices):
        for invoice in invoices:
            if invoice.type == 'out':
                invoice.check_invoice_type()
            elif invoice.type == 'in':
                invoice.pre_validate_fields()
                invoice.check_unique_reference()
        super(Invoice, cls).validate_invoice(invoices)

    def check_invoice_type(self):
        if not self.company.party.iva_condition:
            self.raise_user_error('missing_company_iva_condition', {
                    'company': self.company.rec_name,
                    })
        if not self.party.iva_condition:
            self.raise_user_error('missing_party_iva_condition', {
                    'party': self.party.rec_name,
                    })
        if not self.invoice_type:
            self.raise_user_error('not_invoice_type')
        if not self.get_tax_identifier():
            self.raise_user_error('miss_tax_identifier')
        if (self.get_tax_identifier() and
                not self.company.party.tax_identifier.type == 'ar_cuit'):
            self.raise_user_error('miss_tax_identifier')

    def check_unique_reference(self):
        invoice = self.search([
            ('id', '!=', self.id),
            ('type', '=', self.type),
            ('party', '=', self.party.id),
            ('tipo_comprobante', '=', self.tipo_comprobante),
            ('reference', '=', self.reference),
            ('state', '!=', 'cancel'),
            ])
        if len(invoice) > 0:
            self.raise_user_error('reference_unique')

    def pre_validate_fields(self):
        if not self.reference and not self.tipo_comprobante:
            self.raise_user_error('in_invoice_validate_failed')

    @fields.depends('party', 'tipo_comprobante', 'type', 'reference')
    def on_change_reference(self):
        if self.type == 'in':
            self.check_unique_reference()

    @fields.depends('pos', 'party', 'type', 'company')
    def on_change_pos(self):
        self.ref_number_from = None
        self.ref_number_to = None

    @fields.depends('pos', 'party', 'lines', 'company', 'total_amount', 'type')
    def on_change_with_invoice_type(self, name=None):
        return self._set_invoice_type_sequence()

    @classmethod
    def _tax_identifier_types(cls):
        types = super(Invoice, cls)._tax_identifier_types()
        types.append('ar_cuit')
        return types

    def _set_invoice_type_sequence(self):
        '''
        Set invoice type field.
        require: pos field must be set first.
        '''
        if not self.pos:
            return None

        PosSequence = Pool().get('account.pos.sequence')
        client_iva = company_iva = None
        credit_note = False

        if self.party:
            client_iva = self.party.iva_condition
        if self.company:
            company_iva = self.company.party.iva_condition
        if self.total_amount and self.total_amount < 0:
            credit_note = True

        if company_iva == 'responsable_inscripto':
            if client_iva is None:
                return
            if client_iva == 'responsable_inscripto':
                kind = 'A'
            elif client_iva == 'consumidor_final':
                kind = 'B'
            elif self.party.vat_number:  # CUIT Argentino
                kind = 'B'
            else:
                kind = 'E'
        else:
            kind = 'C'
            if self.party and self.party.vat_number_afip_foreign:  # Id AFIP Foraneo
                kind = 'E'

        invoice_type, invoice_type_desc = INVOICE_TYPE_AFIP_CODE[
            (self.type, credit_note, kind)
            ]
        sequences = PosSequence.search([
            ('pos', '=', self.pos),
            ('invoice_type', '=', invoice_type)
            ])
        if len(sequences) == 0:
            self.raise_user_error('missing_sequence', invoice_type_desc)
        elif len(sequences) > 1:
            self.raise_user_error('too_many_sequences', invoice_type_desc)
        else:
            sequence, = sequences
        return sequence.id

    def set_pyafipws_concept(self):
        '''
        set pyafipws_concept researching the product lines.
        '''
        products = {'1': 0, '2': 0}
        self.pyafipws_concept = ''
        for line in self.lines:
            if line.product:
                if line.product.type == 'goods':
                    products['1'] += 1
                if line.product.type == 'service':
                    products['2'] += 1

        if products['1'] != 0 and products['2'] != 0:
            self.pyafipws_concept = '3'
        elif products['1'] != 0:
            self.pyafipws_concept = '1'
        elif products['2'] != 0:
            self.pyafipws_concept = '2'

    def set_pyafipws_billing_dates(self):
        '''
        set pyafipws_billing_dates by invoice_date.
        '''
        today = Pool().get('ir.date').today()
        if self.invoice_date:
            year = int(self.invoice_date.strftime("%Y"))
            month = int(self.invoice_date.strftime("%m"))
        else:
            year = int(today.strftime("%Y"))
            month = int(today.strftime("%m"))
        self.pyafipws_billing_start_date = date(year, month, 1)
        self.pyafipws_billing_end_date = date(year, month,
            monthrange(year, month)[1])

    def _credit(self):
        pool = Pool()
        PosSequence = pool.get('account.pos.sequence')
        Date = pool.get('ir.date')

        credit = super(Invoice, self)._credit()
        if self.type == 'in':
            invoice_type, invoice_type_desc = INVOICE_CREDIT_AFIP_CODE[
                str(int(self.tipo_comprobante))
                ]
            credit.tipo_comprobante = invoice_type.rjust(3, '0')
            credit.reference = None
            return credit

        credit.pos = self.pos
        credit.invoice_date = Date.today()
        invoice_type, invoice_type_desc = INVOICE_CREDIT_AFIP_CODE[
            (self.invoice_type.invoice_type)
            ]
        sequences = PosSequence.search([
            ('pos', '=', credit.pos),
            ('invoice_type', '=', invoice_type)
            ])
        if len(sequences) == 0:
            self.raise_user_error('missing_sequence', invoice_type_desc)
        elif len(sequences) > 1:
            self.raise_user_error('too_many_sequences', invoice_type_desc)
        else:
            credit.invoice_type = sequences[0]

        if self.pos.pos_type == 'electronic':
            credit.pyafipws_concept = self.pyafipws_concept
            if self.pyafipws_concept in ['2', '3']:
                credit.pyafipws_billing_start_date = (
                    self.pyafipws_billing_start_date)
                credit.pyafipws_billing_end_date = (
                    self.pyafipws_billing_end_date)

        if self.invoice_type.invoice_type in ['19', '20', '21']:
            credit.pyafipws_incoterms = self.pyafipws_incoterms
            credit.pyafipws_licenses = self.pyafipws_licenses

        ref_number = self.number if self.type == 'out' else self.reference
        credit.description = 'Ref. Nro. %s' % ref_number
        return credit

    def get_next_number(self, pattern=None):
        pool = Pool()
        SequenceStrict = pool.get('ir.sequence.strict')
        Sequence = pool.get('ir.sequence')
        Period = pool.get('account.period')

        if pattern is None:
            pattern = {}
        else:
            pattern = pattern.copy()

        period_id = Period.find(
            self.company.id, date=self.accounting_date or self.invoice_date,
            test_state=self.type != 'in')

        period = Period(period_id)
        fiscalyear = period.fiscalyear
        pattern.setdefault('company', self.company.id)
        pattern.setdefault('fiscalyear', fiscalyear.id)
        pattern.setdefault('period', period.id)
        invoice_type = self.type
        if (all(l.amount < 0 for l in self.lines if l.product)
                and self.total_amount < 0):
            invoice_type += '_credit_note'
        else:
            invoice_type += '_invoice'

        for invoice_sequence in fiscalyear.invoice_sequences:
            if invoice_sequence.match(pattern):
                sequence = getattr(
                    invoice_sequence, '%s_sequence' % invoice_type)
                break
        else:
            self.raise_user_error('no_invoice_sequence', {
                    'invoice': self.rec_name,
                    'fiscalyear': fiscalyear.rec_name,
                    })
        with Transaction().set_context(date=self.invoice_date):
            if self.type == 'out':
                number = Sequence.get_id(self.invoice_type.invoice_sequence.id)
                return '%05d-%08d' % (self.pos.number, int(number))
            return SequenceStrict.get_id(sequence.id)

    def _get_move_line(self, date, amount):
        line = super(Invoice, self)._get_move_line(date, amount)
        ref_number = self.number if self.type == 'out' else self.reference
        line.description = '%s Nro. %s' % (self.party.name, ref_number)
        if self.description:
            line.description += ' / %s' % self.description
        return line

    @classmethod
    @ModelView.button
    @Workflow.transition('posted')
    def post(cls, invoices):
        pool = Pool()
        Move = pool.get('account.move')
        Pos = pool.get('account.pos')
        Date = pool.get('ir.date')

        invoices_wsfe = {}
        invoices_wsfe_to_recover = []
        point_of_sales = Pos.search([
            ('pos_type', '=', 'electronic')
            ])
        for pos in point_of_sales:
            pos_number = str(pos.number)
            invoices_wsfe[pos_number] = {}
            for pos_sequence in pos.pos_sequences:
                invoices_wsfe[pos_number][pos_sequence.invoice_type] = []

        for invoice in invoices:
            if invoice.type == 'out':
                invoice.check_invoice_type()
                if (invoice.pos and invoice.pos.pos_type == 'electronic' and
                        invoice.pos.pyafipws_electronic_invoice_service ==
                        'wsfe'):
                    # web service == wsfe invoices go throw batch.
                    if invoice.number and invoice.pyafipws_cae:
                        invoices_wsfe_to_recover.append(invoice)
                    else:
                        invoices_wsfe[str(invoice.pos.number)][
                            invoice.invoice_type.invoice_type].append(invoice)
                    invoices.remove(invoice)

        cls.consultar_and_recover(invoices_wsfe_to_recover)

        moves = []
        for invoice in invoices:
            if invoice.type == 'out':
                invoice.check_invoice_type()
                if invoice.pos:
                    if invoice.pos.pos_type == 'electronic':
                        ws = cls.get_ws_afip(invoice)
                        (ws, error) = invoice.create_pyafipws_invoice(ws,
                            batch=False)
                        (ws, msg) = invoice.request_cae(ws)
                        result = invoice.process_afip_result(ws, msg=msg)
                        Transaction().commit()
                        if result is False:
                            logger.error(
                                'ErrorCAE: %s\nFactura: %s, %s\nEntidad: %s\nXmlRequest: %s\n'
                                'XmlResponse: %s\n',
                                    repr(msg.encode('ascii', 'ignore').strip()),
                                    invoice.id, invoice.type, invoice.party.rec_name,
                                    repr(ws.XmlRequest), repr(ws.XmlResponse))
                            cls.raise_user_error('rejected_invoices', {
                                'invoice': invoice.id,
                                'msg': (
                                    invoice.transactions[-1].pyafipws_message),
                                #'party': invoice.party.rec_name,
                                })
                    elif invoice.pos.pos_type == 'fiscal_printer':
                        if invoice.pos.pos_daily_report:
                            if not invoice.invoice_date and invoice.type == 'out':
                                invoice.invoice_date = Date.today()
                            invoice.number = '%05d-%08d:%d' % \
                                (invoice.pos.number, int(invoice.ref_number_from),
                                 int(invoice.ref_number_to))
                        else:
                            #TODO: Implement fiscal printer integration
                            cls.fiscal_printer_invoice_post()

            cls.set_number([invoice])
            move = invoice.get_move()
            if move != invoice.move:
                invoice.move = move
                moves.append(move)
            if invoice.state != 'posted':
                invoice.state = 'posted'
        if moves:
            Move.save(moves)
        cls.save(invoices)
        Move.post([i.move for i in invoices if i.move.state != 'posted'])

        error_invoices = []
        for pos, value_dict in list(invoices_wsfe.items()):
            for key, invoices_by_type in list(value_dict.items()):
                (pre_rejected_invoice, rejected_invoice) = \
                    cls.post_wsfe([i for i in invoices_by_type
                            if not (i.pyafipws_cae and i.number)])
                Transaction().commit()
                if rejected_invoice:
                    error_invoices.append(rejected_invoice)
                elif pre_rejected_invoice:
                    error_invoices.append(pre_rejected_invoice)
        if error_invoices:
            cls.raise_user_error('rejected_invoices', {
                'invoices': ','.join([str(i.id) for i in error_invoices]),
                'msg': ','.join([i.transactions[-1].pyafipws_message for i \
                            in error_invoices if i.transactions]),
                })

        # Bug: https://github.com/tryton-ar/account_invoice_ar/issues/38
        #for invoice in invoices:
        #    if invoice.type == 'out':
        #        invoice.print_invoice()

    @classmethod
    def consultar_and_recover(cls, invoices):
        pool = Pool()
        Move = pool.get('account.move')
        AFIP_Transaction = pool.get('account_invoice_ar.afip_transaction')
        moves = []
        for invoice in invoices:
            ws = cls.get_ws_afip(invoice=invoice)
            if not invoice.invoice_date:
                cls.raise_user_error('missing_invoice_date')
            ws.Reprocesar = True
            ws, error = invoice.create_pyafipws_invoice(ws)
            cbte_nro = int(invoice.number[-8:])
            cae = ws.CompConsultar(invoice.invoice_type.invoice_type,
                invoice.pos.number, cbte_nro, reproceso=True)
            if cae and ws.EmisionTipo == 'CAE':
                # la factura se recupera y puede pasar a estado posted
                logger.info('se ha reprocesado invoice %s', invoice.id)
                if not invoice.transactions:
                    invoice.save_afip_tr(ws, msg='Reprocesar=S')
                move = invoice.get_move()
                if move != invoice.move:
                    invoice.move = move
                    moves.append(move)
                if invoice.state != 'posted':
                    invoice.state = 'posted'
            else:
                # raise error, los datos enviados no existen en AFIP.
                logger.error('diferencias entre el comprobante %s '
                    'que tiene AFIP y el de tryton.', invoice.id)
                cls.raise_user_error('reprocesar_invoice_dif')
        if moves:
            Move.save(moves)
        cls.save(invoices)
        Move.post([i.move for i in invoices if i.move.state != 'posted'])

    @classmethod
    def fiscal_printer_invoice_post(cls, invoice=None):
        #TODO: Implement fiscal printer integration
        pass

    @classmethod
    def get_ws_afip(cls, invoice=None, batch=False):
        '''
        Connect to WSAA AFIP and get webservice wsfe or wsfex
        '''
        if batch is False and invoice:
            service = invoice.pos.pyafipws_electronic_invoice_service
        elif batch is True:
            service = 'wsfe'
        else:
            logger.error('AFIP web service is unknown')
            cls.raise_user_error('webservice_unknown')

        (company, auth_data) = cls.authenticate_afip(service=service)
        # TODO: get wsdl url from DictField?
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

        ws = cls.conect_afip(ws, WSDL, company.party.vat_number, auth_data)
        return ws

    @classmethod
    def authenticate_afip(cls, service='wsfe'):
        '''
        Authenticate to webservice WSAA
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
        return (company, auth_data)

    @classmethod
    def conect_afip(cls, ws, wsdl, vat_number, auth_data):
        '''
        Connect to WSAA webservice
        '''
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
        return ws

    @classmethod
    def post_wsfe(cls, invoices):
        '''
        Post batch invoices.
        '''
        if invoices == []:
            return ([], [])

        Move = Pool().get('account.move')
        moves = []
        ws = cls.get_ws_afip(batch=True)
        reg_x_req = ws.CompTotXRequest()    # cant max. comprobantes
        cant_invoices = len(invoices)
        pre_approved_invoices = []
        approved_invoices = []
        pre_rejected_invoice = None
        rejected_invoice = None

        # before set_number, validate some stuff.
        # get only invoices that pass validations.
        # TODO: Add those validations to validate_invoice method.
        for invoice in invoices:
            # TODO: usar try/except
            (ws, error) = invoice.create_pyafipws_invoice(ws, batch=True)
            if error:
                if pre_rejected_invoice is None:
                    pre_rejected_invoice = invoice
            else:
                pre_approved_invoices.append(invoice)

        tmp_ = [pre_approved_invoices[i:i+reg_x_req] for i in
            range(0, len(pre_approved_invoices), reg_x_req)]
        for chunk_invoices in tmp_:
            ws.IniciarFacturasX()
            invoices_added_to_ws = []
            chunk_with_errors = False
            cls.set_number(chunk_invoices)
            for invoice in chunk_invoices:
                (ws, error) = invoice.create_pyafipws_invoice(ws, batch=True)
                if error is False:
                    ws.AgregarFacturaX()
                    invoices_added_to_ws.append(invoice)
            # CAESolicitarX
            try:
                cant_solicitadax = ws.CAESolicitarX()
                logger.info('wsfe batch invoices posted: %s' % cant_solicitadax)
            except Exception as e:
                logger.error('CAESolicitarX msg: %s' % str(e))

            # Process results:
            cant = 0
            for invoice in invoices_added_to_ws:
                ws.LeerFacturaX(cant)
                cant += 1
                result = invoice.process_afip_result(ws)
                if result:
                    approved_invoices.append(invoice)
                else:
                    chunk_with_errors = True
                    invoice.number = None
                    invoice.invoice_date = None
                    if rejected_invoice is None:
                        rejected_invoice = invoice
                        logger.error(
                            'Factura: %s, %s\nEntidad: %s\nXmlRequest: %s\n'
                            'XmlResponse: %s\n', rejected_invoice.id,
                            rejected_invoice.type, rejected_invoice.party.rec_name,
                            repr(ws.XmlRequest), repr(ws.XmlResponse))

            if chunk_with_errors:
                # Set next sequence number to be the last cbte_nro_afip + 1.
                sequence = rejected_invoice.invoice_type.invoice_sequence
                tipo_cbte = rejected_invoice.invoice_type.invoice_type
                punto_vta = rejected_invoice.pos.number
                cbte_nro_afip = ws.CompUltimoAutorizado(tipo_cbte, punto_vta)
                sequence.update_sql_sequence(int(cbte_nro_afip) + 1)

        for invoice in approved_invoices:
            move = invoice.get_move()
            if move != invoice.move:
                invoice.move = move
                moves.append(move)
            if invoice.state != 'posted':
                invoice.state = 'posted'
        if moves:
            Move.save(moves)
        cls.save(invoices)
        if moves:
            Move.post([i.move for i in approved_invoices
                if i.move.state != 'posted'])
        return (pre_rejected_invoice, rejected_invoice)

    def create_pyafipws_invoice(self, ws, batch=False):
        '''
        Create invoice as pyafipws requires and call to ws.CrearFactura(args).
        '''

        def strip_accents(text):
            """
            Strip accents from input String.

            :param text: The input string.
            :type text: String.

            :returns: The processed String.
            :rtype: String.
            """
            try:
                text = unicode(text, 'utf-8')
            except (TypeError, NameError): # unicode is a default on python 3
                pass
            text = normalize('NFD', text)
            text = text.encode('ascii', 'ignore')
            text = text.decode("utf-8")
            return str(text)

        # if already authorized (electronic invoice with CAE), ignore
        #if self.pyafipws_cae:
        #    logger.info('invoice_has_cae: Invoice (%s) has CAE %s',
        #        (self.number, self.pyafipws_cae))
        #    return (ws, True)

        # if pyafipws_concept is empty
        if not self.pyafipws_concept:
            if batch:
                logger.error('missing_pyafipws_concept:field pyafipws_concept '
                    'is missing at invoice "%s"' % self.rec_name)
                return (ws, True)
            self.raise_user_error('missing_pyafipws_concept')
        if (self.pyafipws_concept in ['2', '3'] and not
                (self.pyafipws_billing_start_date or
                    self.pyafipws_billing_end_date)):
                if batch:
                    logger.error('missing_pyafipws_billing_date:billing_dates '
                        'fields are missing at invoice "%s"' % self.rec_name)
                    return (ws, True)
                self.raise_user_error('missing_pyafipws_billing_date')
        # get the electronic invoice type, point of sale and service:
        pool = Pool()
        Sequence = pool.get('ir.sequence')
        Date = pool.get('ir.date')

        # get the electronic invoice type, point of sale and service:
        tipo_cbte = self.invoice_type.invoice_type
        punto_vta = self.pos.number
        service = self.pos.pyafipws_electronic_invoice_service

        # get the last 8 digit of the invoice number
        if self.number:
            cbte_nro = int(self.number[-8:])
        else:
            cbte_nro = int(Sequence(
                self.invoice_type.invoice_sequence.id).get_number_next(''))

        # get the last invoice number registered in AFIP
        if ws.Reprocesar:
            cbte_nro_next = cbte_nro
        elif batch:
            cbte_nro_next = cbte_nro
        else:
            if service == 'wsfe' or service == 'wsmtxca':
                cbte_nro_afip = ws.CompUltimoAutorizado(tipo_cbte, punto_vta)
            elif service == 'wsfex':
                cbte_nro_afip = ws.GetLastCMP(tipo_cbte, punto_vta)
            cbte_nro_next = int(cbte_nro_afip or 0) + 1
            # verify that the invoice is the next one to be registered in AFIP
            if cbte_nro != cbte_nro_next:
                if batch:
                    logger.error('invalid_invoice_number: Invoice: %s, try to '
                        'assign invoice number: %d when AFIP is waiting for '
                        '%d' % (self.id, cbte_nro, cbte_nro_next))
                    return (ws, True)
                self.raise_user_error('invalid_invoice_number', (cbte_nro,
                    cbte_nro_next))

        # invoice number range (from - to) and date:
        cbte_nro = cbt_desde = cbt_hasta = cbte_nro_next

        if self.invoice_date:
            fecha_cbte = self.invoice_date.strftime('%Y-%m-%d')
        else:
            fecha_cbte = Date.today().strftime('%Y-%m-%d')

        if service != 'wsmtxca':
            fecha_cbte = fecha_cbte.replace('-', '')

        # due and billing dates only for concept 'services'
        concepto = tipo_expo = int(self.pyafipws_concept or 0)
        if int(concepto) != 1:

            payments = []
            if self.payment_term:
                payments = self.payment_term.compute(self.total_amount,
                    self.currency)
            if payments == []:
                last_payment = date.today()
            else:
                last_payment = max(payments, key=lambda x: x[0])[0]
            fecha_venc_pago = last_payment.strftime('%Y-%m-%d')
            if service != 'wsmtxca':
                fecha_venc_pago = fecha_venc_pago.replace('-', '')
            if self.pyafipws_billing_start_date:
                fecha_serv_desde = self.pyafipws_billing_start_date.strftime(
                    '%Y-%m-%d')
                if service != 'wsmtxca':
                    fecha_serv_desde = fecha_serv_desde.replace('-', '')
            else:
                fecha_serv_desde = None
            if self.pyafipws_billing_end_date:
                fecha_serv_hasta = self.pyafipws_billing_end_date.strftime(
                    '%Y-%m-%d')
                if service != 'wsmtxca':
                    fecha_serv_hasta = fecha_serv_hasta.replace('-', '')
            else:
                fecha_serv_hasta = None
        else:
            fecha_venc_pago = fecha_serv_desde = fecha_serv_hasta = None

        # customer tax number:
        nro_doc = None
        if self.party.vat_number:
            nro_doc = self.party.vat_number
            tipo_doc = 80  # CUIT
        else:
            for identifier in self.party.identifiers:
                if identifier.type == 'ar_dni':
                    nro_doc = identifier.code
                    tipo_doc = 96
            if nro_doc is None:
                nro_doc = '0'  # only 'consumidor final'
                tipo_doc = 99  # consumidor final

        # invoice amount totals:
        imp_total = str('%.2f' % abs(self.total_amount))
        imp_subtotal = str('%.2f' % abs(self.untaxed_amount)) # TODO
        imp_tot_conc = Decimal('0') # No gravado
        imp_neto = Decimal('0')
        imp_iva, imp_trib = self._get_imp_total_iva_and_trib(service)
        imp_op_ex = '0.00' # Exento TODO: issue#136

        if self.company.party.iva_condition in ['exento', 'monotributo']:
            imp_neto = abs(self.untaxed_amount)
            imp_tot_conc = Decimal('0')
        else:
            for line in self.lines:
                if line.taxes:
                    imp_neto += abs(line.amount)
                else:
                    imp_tot_conc += abs(line.amount)

        imp_neto = str('%.2f' % imp_neto)
        imp_tot_conc = str('%.2f' % imp_tot_conc)

        if self.company.currency.rate == Decimal('0'):
            if self.party.vat_number_afip_foreign:
                if batch:
                    logger.error('missing_currency_rate: Invoice: %s, '
                        'rate is not setted.' % self.id)
                    return (ws, True)
                self.raise_user_error('missing_currency_rate')
            else:
                ctz = 1
        elif self.company.currency.rate == Decimal('1'):
            ctz = 1 / self.currency.rate
        else:
            ctz = self.company.currency.rate / self.currency.rate

        if self.currency.code == 'ARS':
            moneda_id = 'PES'
        else:
            moneda_id = {'USD': 'DOL', 'EUR': '060'}[self.currency.code]

        moneda_ctz = str('%.2f' % ctz)

        # foreign trade data: export permit, country code, etc.:
        if self.pyafipws_incoterms:
            incoterms = self.pyafipws_incoterms
            incoterms_ds = dict(self._fields['pyafipws_incoterms'].selection)[
                self.pyafipws_incoterms]
        else:
            incoterms = incoterms_ds = None

        if incoterms is None and incoterms_ds is None and service == 'wsfex':
            if batch:
                logger.error('missing_pyafipws_incoterms: Invoice: %s '
                    'field is not setted.' % self.id)
                return (ws, True)
            self.raise_user_error('missing_pyafipws_incoterms')

        if int(tipo_cbte) == 19 and tipo_expo == 1:
            permiso_existente = 'N' or 'S'  # not used now
        else:
            permiso_existente = ''
        obs_generales = self.comment
        if self.payment_term:
            forma_pago = self.payment_term.name
            obs_comerciales = self.payment_term.name
        else:
            forma_pago = obs_comerciales = None
        idioma_cbte = 1  # invoice language: spanish / español

        # customer data (foreign trade):
        nombre_cliente = self.party.name
        if self.party.vat_number:
            # Si tenemos vat_number, entonces tenemos CUIT Argentino
            # use the Argentina AFIP's global CUIT for the country:
            cuit_pais_cliente = self.party.vat_number
            id_impositivo = None
        elif self.party.vat_number_afip_foreign:
                # use the VAT number directly
                id_impositivo = None
                cuit_pais_cliente = self.party.vat_number_afip_foreign
        else:
            cuit_pais_cliente = id_impositivo = None
        if self.invoice_address:
            address = self.invoice_address
            domicilio_cliente = ' - '.join([
                    address.name or '',
                    address.street or '',
                    address.zip or '',
                    address.city or '',
                    ])
        else:
            domicilio_cliente = ''
        if self.party.vat_number_afip_foreign:
            for identifier in self.party.identifiers:
                if identifier.type == 'ar_foreign':
                    # map ISO country code to AFIP destination country code:
                    pais_dst_cmp = identifier.afip_country.code

        # create the invoice internally in the helper
        if service == 'wsfe':
            ws.CrearFactura(concepto, tipo_doc, nro_doc, tipo_cbte, punto_vta,
                cbt_desde, cbt_hasta, imp_total, imp_tot_conc, imp_neto,
                imp_iva, imp_trib, imp_op_ex, fecha_cbte, fecha_venc_pago,
                fecha_serv_desde, fecha_serv_hasta,
                moneda_id, moneda_ctz)
        elif service == 'wsmtxca':
            ws.CrearFactura(concepto, tipo_doc, nro_doc, tipo_cbte, punto_vta,
                cbt_desde, cbt_hasta, imp_total, imp_tot_conc, imp_neto,
                imp_subtotal, imp_trib, imp_op_ex, fecha_cbte,
                fecha_venc_pago, fecha_serv_desde, fecha_serv_hasta,
                moneda_id, moneda_ctz, obs_generales)
        elif service == 'wsfex':
            ws.CrearFactura(tipo_cbte, punto_vta, cbte_nro, fecha_cbte,
                imp_total, tipo_expo, permiso_existente, pais_dst_cmp,
                nombre_cliente, cuit_pais_cliente, domicilio_cliente,
                id_impositivo, moneda_id, moneda_ctz, obs_comerciales,
                obs_generales, forma_pago, incoterms,
                idioma_cbte, incoterms_ds)

        # analyze VAT (IVA) and other taxes (tributo):
        if service in ('wsfe', 'wsmtxca'):
            for tax_line in self.taxes:
                tax = tax_line.tax
                if tax.group is None:
                    if batch:
                        logger.error('tax_without_group: Invoice: %s, tax: %s'
                            % (self.id, tax.name))
                        return (ws, True)
                    self.raise_user_error('tax_without_group', {
                            'tax': tax.name,
                            })
                if 'iva' in tax.group.code.lower():
                    iva_id = IVA_AFIP_CODE[tax.rate]
                    base_imp = ('%.2f' % abs(tax_line.base))
                    importe = ('%.2f' % abs(tax_line.amount))
                    ws.AgregarIva(iva_id, base_imp, importe)
                else:
                    if 'nacional' in tax.group.code.lower():
                        tributo_id = 1  # nacional
                    elif 'iibb' in tax.group.code.lower():
                        tributo_id = 2  # provincial
                    elif 'municipal' in tax.group.code.lower():
                        tributo_id = 3  # municipal
                    elif 'interno' in tax.group.code.lower():
                        tributo_id = 3  # municipal
                    else:
                        tributo_id = 99
                    desc = tax.name
                    base_imp = ('%.2f' % abs(tax_line.base))
                    importe = ('%.2f' % abs(tax_line.amount))
                    alic = '%.2f' % abs(tax.rate * 100)
                    # add the other tax detail in the helper
                    ws.AgregarTributo(tributo_id, desc, base_imp, alic,
                        importe)

                ## Agrego un item:
                #codigo = 'PRO1'
                #ds = 'Producto Tipo 1 Exportacion MERCOSUR ISO 9001'
                #qty = 2
                #precio = '150.00'
                #umed = 1 # Ver tabla de parámetros (unidades de medida)
                #bonif = '50.00'
                #imp_total = '250.00'  # importe total final del artículo
        # analize line items - invoice detail
        # umeds
        # Parametros. Unidades de Medida, etc.
        # https://code.google.com/p/pyafipws/wiki/WSFEX#WSFEX/
        #     RECEX_Parameter_Tables
        if service in ('wsfex', 'wsmtxca'):
            for line in self.lines:
                if line.product:
                    codigo = line.product.code
                else:
                    codigo = 0
                ds = strip_accents(line.description)
                qty = abs(line.quantity)
                umed = 7  # FIXME: (7 - unit)
                precio = str(line.unit_price)
                importe_total = str(abs(line.amount))
                bonif = None  # line.discount
                #for tax in line.taxes:
                #    if tax.group.name == 'IVA':
                #        iva_id = IVA_AFIP_CODE[tax.rate]
                #        imp_iva = importe * tax.rate
                #if service == 'wsmtxca':
                #    ws.AgregarItem(u_mtx, cod_mtx, codigo, ds, qty, umed,
                #            precio, bonif, iva_id, imp_iva, importe+imp_iva)
                if service == 'wsfex':
                    ws.AgregarItem(codigo, ds, qty, umed, precio,
                        importe_total, bonif)

            if service == 'wsfex':
                for export_license in self.pyafipws_licenses:
                    ws.AgregarPermiso(
                        export_license.license_id,
                        export_license.afip_country.code)
        return (ws, False)

    def request_cae(self, ws):
        '''
        Request to AFIP the invoice Authorization Electronic Code (CAE).
        '''
        service = self.pos.pyafipws_electronic_invoice_service
        msg = ''
        try:
            if service == 'wsfe':
                ws.CAESolicitar()
            elif service == 'wsmtxca':
                ws.AutorizarComprobante()
            elif service == 'wsfex':
                ws.Authorize(self.id)
        except Exception as e:
            if ws.Excepcion:
                # get the exception already parsed by the helper
                #import ipdb; ipdb.set_trace()  # XXX BREAKPOINT
                msg = ws.Excepcion + ' ' + str(e)
            else:
                # avoid encoding problem when reporting exceptions to the user:
                import traceback
                import sys
                msg = traceback.format_exception_only(sys.exc_info()[0],
                    sys.exc_info()[1])[0]
        return (ws, msg)

    def save_afip_tr(self, ws, msg=''):
        '''
        store afip XmlRequest/XmlResponse.
        '''
        AFIP_Transaction = Pool().get('account_invoice_ar.afip_transaction')
        message = '\n'.join([ws.Obs or '', ws.ErrMsg or '', msg])
        message = message.encode('ascii', 'ignore').strip()
        afip_tr = AFIP_Transaction()
        afip_tr.invoice = self
        afip_tr.pyafipws_result = ws.Resultado
        afip_tr.pyafipws_message = message.decode('utf-8')
        afip_tr.pyafipws_xml_request = ws.XmlRequest.decode('utf-8')
        afip_tr.pyafipws_xml_response = ws.XmlResponse.decode('utf-8')
        afip_tr.save()

    def process_afip_result(self, ws, msg=''):
        '''
        Process CAE and store results
        '''
        self.save_afip_tr(ws, msg)
        if ws.CAE:
            tipo_cbte = self.invoice_type.invoice_type
            punto_vta = self.pos.number

            vto = ''
            if isinstance(ws, WSFEv1):
                vto = ws.Vencimiento
            elif isinstance(ws, WSFEXv1):
                vto = ws.FchVencCAE
            cae_due = ''.join([c for c in str(vto)
                    if c.isdigit()])
            bars = ''.join([str(ws.Cuit), '%02d' % int(tipo_cbte),
                    '%05d' % int(punto_vta), str(ws.CAE), cae_due])
            bars = bars + self.pyafipws_verification_digit_modulo10(bars)
            pyafipws_cae_due_date = vto or None
            if not '-' in vto:
                pyafipws_cae_due_date = '-'.join([vto[:4], vto[4:6], vto[6:8]])
            self.pyafipws_cae = ws.CAE
            self.pyafipws_barcode = bars
            self.pyafipws_cae_due_date = pyafipws_cae_due_date
            return True
        return False

    def pyafipws_verification_digit_modulo10(self, codigo):
        'Calculate the verification digit "modulo 10"'
        # http://www.consejo.org.ar/Bib_elect/diciembre04_CT/documentos/
        #     rafip1702.htm
        # Step 1: sum all digits in odd positions, left to right
        codigo = codigo.strip()
        if not codigo or not codigo.isdigit():
            return ''
        etapa1 = sum([int(c) for i, c in enumerate(codigo) if not i % 2])
        # Step 2: multiply the step 1 sum by 3
        etapa2 = etapa1 * 3
        # Step 3: start from the left, sum all the digits in even positions
        etapa3 = sum([int(c) for i, c in enumerate(codigo) if i % 2])
        # Step 4: sum the results of step 2 and 3
        etapa4 = etapa2 + etapa3
        # Step 5: the minimun value that summed to step 4 is a multiple of 10
        digito = 10 - (etapa4 - (int(etapa4 / 10) * 10))
        if digito == 10:
            digito = 0
        return str(digito)

    # @return (imp_iva, imp_trib)
    def _get_imp_total_iva_and_trib(self, service):
        # analyze VAT (IVA) and other taxes (tributo):
        imp_iva = Decimal('0')
        imp_trib = Decimal('0')
        if service in ('wsfe', 'wsmtxca'):
            for tax_line in self.taxes:
                tax = tax_line.tax
                if 'iva' in tax.group.code.lower():
                    imp_iva += tax_line.amount
                else:
                    imp_trib += tax_line.amount

        return ('%.2f' % abs(imp_iva), '%.2f' % abs(imp_trib))


class InvoiceExportLicense(ModelSQL, ModelView):
    'Invoice Export License'
    __name__ = 'account.invoice.export.license'

    invoice = fields.Many2One('account.invoice', 'Invoice',
        ondelete='CASCADE', select=True, required=True)
    license_id = fields.Char('License Id', required=True)
    afip_country = fields.Many2One('afip.country', 'AFIP Country',
        required=True)

    @classmethod
    def __register__(cls, module_name):
        super(InvoiceExportLicense, cls).__register__(module_name)
        TableHandler = backend.get('TableHandler')
        pool = Pool()
        afip_country = pool.get('afip.country').__table__()
        table = cls.__table__()
        cursor = Transaction().connection.cursor()
        table_handler = TableHandler(cls, module_name)
        # Migration legacy: country -> afip_country
        if table_handler.column_exist('country'):
            cursor.execute(*table.select(table.id, table.country))
            for id, country in cursor.fetchall():
                if country != '':
                    cursor.execute(*afip_country.select(afip_country.id,
                            where=(afip_country.code == country)))
                    row, = cursor_dict(cursor)
                    cursor.execute(*table.update(
                        [table.afip_country], [row['id']],
                        where=(table.id == id)))
            table_handler.drop_column('country')


class InvoiceReport(metaclass=PoolMeta):
    __name__ = 'account.invoice'

    @classmethod
    def get_context(cls, records, data):
        pool = Pool()
        User = pool.get('res.user')
        Invoice = pool.get('account.invoice')

        report_context = super(InvoiceReport, cls).get_context(records, data)
        invoice = records[0]

        user = User(Transaction().user)
        report_context['company'] = user.company
        report_context['barcode_img'] = cls._get_pyafipws_barcode_img(Invoice,
            invoice)
        report_context['condicion_iva'] = cls._get_condicion_iva(user.company)
        report_context['iibb_type'] = cls._get_iibb_type(user.company)
        report_context['vat_number'] = cls._get_vat_number(user.company)
        report_context['tipo_comprobante'] = cls._get_tipo_comprobante(Invoice,
            invoice)
        report_context['nombre_comprobante'] = cls._get_nombre_comprobante(
            Invoice, invoice)
        report_context['codigo_comprobante'] = cls._get_codigo_comprobante(
            Invoice, invoice)
        report_context['condicion_iva_cliente'] = (
            cls._get_condicion_iva_cliente(Invoice, invoice))
        report_context['vat_number_cliente'] = cls._get_vat_number_cliente(
            Invoice, invoice)
        report_context['dni_number_cliente'] = cls._get_dni_number_cliente(
            Invoice, invoice)
        report_context['get_impuestos'] = cls.get_impuestos
        report_context['get_line_amount'] = cls.get_line_amount
        report_context['get_taxes'] = cls.get_taxes
        report_context['get_subtotal'] = cls.get_subtotal
        return report_context

    @classmethod
    def get_line_amount(cls, line_amount, line_taxes):
        total = abs(line_amount)
        taxes = cls.get_line_taxes(line_taxes)
        for tax in taxes:
            if tax.tax.rate:
                total = total + (line_amount * tax.tax.rate)
            elif tax.tax.amount:
                total = total + abs(tax.tax.amount)
        return total

    @classmethod
    def get_subtotal(cls, invoice):
        subtotal = abs(invoice.untaxed_amount)
        taxes = cls.get_line_taxes(invoice.taxes)
        for tax in taxes:
            subtotal += abs(tax.amount)
        return subtotal

    @classmethod
    def get_impuestos(cls, invoice):
        if hasattr(invoice.invoice_type, 'invoice_type') is False:
            return abs(invoice.tax_amount)

        tax_amount = Decimal('0')
        taxes = cls.get_taxes(invoice.taxes)
        for tax in taxes:
            tax_amount += abs(tax.amount)
        return tax_amount

    @classmethod
    def get_line_taxes(cls, taxes):
        logger.debug('get_line_taxes: %s' % repr(taxes))
        res = []
        invoice_type_string = ''
        if len(taxes) > 0 and hasattr(taxes[0].invoice.invoice_type,
                'invoice_type'):
            invoice_type_string = \
                taxes[0].invoice.invoice_type.invoice_type_string[-1]

        if invoice_type_string != 'A':
            for tax in taxes:
                if 'iva' in tax.tax.group.code.lower():
                    res.append(tax)
        return res

    @classmethod
    def get_taxes(cls, taxes):
        logger.debug('get_taxes: %s' % repr(taxes))
        res = []
        invoice_type_string = ''
        if len(taxes) > 0 and hasattr(taxes[0].invoice.invoice_type,
                'invoice_type'):
            invoice_type_string = \
                taxes[0].invoice.invoice_type.invoice_type_string[-1]

        if invoice_type_string == 'A':
            res = taxes
        elif invoice_type_string == 'B':
            for tax in taxes:
                if 'iva' not in tax.tax.group.code.lower():
                    res.append(tax)
        return res

    @classmethod
    def _get_condicion_iva_cliente(cls, Invoice, invoice):
        return dict(invoice.party._fields['iva_condition'].selection)[
            invoice.party.iva_condition]

    @classmethod
    def _get_vat_number_cliente(cls, Invoice, invoice):
        value = invoice.party.vat_number
        if value:
            return '%s-%s-%s' % (value[:2], value[2:-1], value[-1])
        return ''

    @classmethod
    def _get_dni_number_cliente(cls, Invoice, invoice):
        value = ''
        for identifier in invoice.party.identifiers:
            if identifier.type == 'ar_dni':
                value = identifier.code
        return value

    @classmethod
    def _get_tipo_comprobante(cls, Invoice, invoice):
        if hasattr(invoice.invoice_type, 'invoice_type'):
            return dict(invoice.invoice_type._fields[
                'invoice_type'].selection)[
                invoice.invoice_type.invoice_type][-1]
        else:
            return ''

    @classmethod
    def _get_nombre_comprobante(cls, Invoice, invoice):
        if hasattr(invoice.invoice_type, 'invoice_type'):
            return dict(invoice.invoice_type._fields[
                'invoice_type'].selection)[
                invoice.invoice_type.invoice_type][3:-2]
        else:
            return ''

    @classmethod
    def _get_codigo_comprobante(cls, Invoice, invoice):
        if hasattr(invoice.invoice_type, 'invoice_type'):
            return dict(invoice.invoice_type._fields[
                'invoice_type'].selection)[
                invoice.invoice_type.invoice_type][:2]
        else:
            return ''
    @classmethod
    def _get_vat_number(cls, company):
        value = company.party.vat_number
        return '%s-%s-%s' % (value[:2], value[2:-1], value[-1])

    @classmethod
    def _get_condicion_iva(cls, company):
        return dict(company.party._fields['iva_condition'].selection)[
                company.party.iva_condition]

    @classmethod
    def _get_iibb_type(cls, company):
        if company.party.iibb_type and company.party.iibb_number:
            if company.party.iibb_type.lower() == 'cm':
                return '%s  %s-%s' % (
                        company.party.iibb_type.upper(),
                        company.party.iibb_number[:3],
                        company.party.vat_number)
            else:
                return '%s %s' % (
                        company.party.iibb_type.upper(),
                        company.party.iibb_number)
        else:
            return ''

    @classmethod
    def _get_pyafipws_barcode_img(cls, Invoice, invoice):
        'Generate the required barcode Interleaved of 7 image using PIL'
        # create the helper:
        pyi25 = PyI25()
        output = BytesIO()
        if not invoice.pyafipws_barcode:
            return
        # call the helper:
        bars = ''.join([c for c in invoice.pyafipws_barcode if c.isdigit()])
        if not bars:
            bars = '00'
        pyi25.GenerarImagen(bars, output, basewidth=3, width=380, height=50,
            extension='PNG')
        image = (output.getvalue(), 'image/jpeg')
        output.close()
        return image
