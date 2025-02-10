# This file is part of the account_invoice_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from pyafipws.wsfev1 import WSFEv1
from pyafipws.wsfexv1 import WSFEXv1
from pyafipws.pyi25 import PyI25
from pyafipws import pyqr
from io import BytesIO
import stdnum.ar.cuit as cuit
import logging
from decimal import Decimal
from datetime import date, datetime
from calendar import monthrange
from unicodedata import normalize

from trytond.model import ModelSQL, Workflow, fields, ModelView, Index
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, And, If, Bool
from trytond.transaction import Transaction
from trytond.model.exceptions import AccessError
from trytond.exceptions import UserError
from trytond.i18n import gettext
from trytond.tools import cursor_dict
from .pos import INVOICE_TYPE_POS
from trytond.modules.account_invoice.exceptions import InvoiceNumberError

logger = logging.getLogger(__name__)

_ZERO = Decimal('0.0')

INVOICE_TYPE_AFIP_CODE = {
    ('out', False, 'A', False): ('1', '01-Factura A'),
    ('out', False, 'A', True): ('201', '201-Factura de Crédito MiPyme A'),
    ('out', False, 'B', False): ('6', '06-Factura B'),
    ('out', False, 'B', True): ('206', '206-Factura de Crédito MiPyme B'),
    ('out', False, 'C', False): ('11', '11-Factura C'),
    ('out', False, 'C', True): ('211', '211-Factura de Crédito MiPyme C'),
    ('out', False, 'E', False): ('19', '19-Factura E'),
    ('out', True, 'A', False): ('3', '03-Nota de Crédito A'),
    ('out', True, 'A', True): ('203', '203-Nota de Crédito MiPyme A'),
    ('out', True, 'B', False): ('8', '08-Nota de Crédito B'),
    ('out', True, 'B', True): ('208', '208-Nota de Crédito MiPyme B'),
    ('out', True, 'C', False): ('13', '13-Nota de Crédito C'),
    ('out', True, 'C', True): ('213', '213-Nota de Crédito MiPyme C'),
    ('out', True, 'E', False): ('21', '21-Nota de Crédito E'),
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
    '27': ('48', '48-Nota de Credito Liquidacion CLASE A'),
    '28': ('43', '43-Nota de Credito Liquidacion CLASE B'),
    '29': ('44', '44-Nota de Credito Liquidacion CLASE C'),
    '51': ('53', '53-NotaS de Credito M'),
    '81': ('112', '112-Tique Nota de Credito A'),
    '82': ('113', '113-Tique Nota de Credito B'),
    '83': ('110', '110-Tique Nota de Credito'),
    '111': ('114', '114-Tique Nota de Credito C'),
    '118': ('119', '119-Tique Nota de Credito M'),
    '201': ('203', '203-Nota de Credito Electronica MiPyMEs (FCE) A'),
    '202': ('203', '203-Nota de Credito Electronica MiPyMEs (FCE) A'),
    '203': ('202', '202-Nota de Debito Electronica MiPyMEs (FCE) A'),
    '206': ('208', '208-Nota de Credito Electronica MiPyMEs (FCE) B'),
    '207': ('208', '208-Nota de Credito Electronica MiPyMEs (FCE) B'),
    '208': ('207', '207-Nota de Debito Electronica MiPyMEs (FCE) B'),
    '211': ('213', '213- Nota de Credito Electronica MiPyMEs (FCE) C'),
    '212': ('213', '213- Nota de Credito Electronica MiPyMEs (FCE) C'),
    '213': ('212', '212- Nota de Debito Electronica MiPyMEs (FCE) C'),
    }

INVOICE_ASOC_AFIP_CODE = {
    '1': [3],
    '2': [1, 3],
    '3': [1, 2],
    '6': [8],
    '7': [6, 8],
    '8': [6, 7],
    '11': [13],
    '12': [11, 13],
    '13': [11, 12],
    '19': [21],
    '20': [19, 21],
    '21': [19, 20],
    '201': [203],
    '202': [201, 203],
    '203': [201, 202],
    '206': [208],
    '207': [206, 208],
    '208': [206, 207],
    '211': [213],
    '212': [211, 213],
    '213': [211, 212],
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
        ondelete='CASCADE', required=True)
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


class InvoiceLine(metaclass=PoolMeta):
    __name__ = 'account.invoice.line'

    @classmethod
    def __register__(cls, module_name):
        table_h = cls.__table_handler__(module_name)
        pyafipws_exento_exist = table_h.column_exist('pyafipws_exento')
        super().__register__(module_name)
        if pyafipws_exento_exist and cls._migrate_pyafipws_exento():
            table_h.drop_column('pyafipws_exento')

    @classmethod
    def _migrate_pyafipws_exento(cls):
        cursor = Transaction().connection.cursor()
        pool = Pool()
        Tax = pool.get('account.tax')
        Invoice = pool.get('account.invoice')
        Line = pool.get('account.invoice.line')
        LineTax = pool.get('account.invoice.line-account.tax')
        InvoiceTax = pool.get('account.invoice.tax')

        line = Line.__table__()
        invoice = Invoice.__table__()
        line_tax = LineTax.__table__()
        invoice_tax = InvoiceTax.__table__()

        try:
            iva_venta_exento, = Tax.search([
                ('group.afip_kind', '=', 'exento'),
                ('group.kind', '=', 'sale'),
                ])
            iva_venta_no_gravado, = Tax.search([
                ('group.afip_kind', '=', 'no_gravado'),
                ('group.kind', '=', 'sale'),
                ])
            iva_compra_exento, = Tax.search([
                ('group.afip_kind', '=', 'exento'),
                ('group.kind', '=', 'purchase'),
                ])
            iva_compra_no_gravado, = Tax.search([
                ('group.afip_kind', '=', 'no_gravado'),
                ('group.kind', '=', 'purchase'),
                ])
        except ValueError:
            return False

        iva_venta_exento_id = iva_venta_exento.id
        iva_venta_no_gravado_id = iva_venta_no_gravado.id
        iva_compra_exento_id = iva_compra_exento.id
        iva_compra_no_gravado_id = iva_compra_no_gravado.id

        computed_taxes = {}
        cursor.execute(*line.join(invoice,
            condition=line.invoice == invoice.id
            ).select(line.id, line.pyafipws_exento, line.invoice,
            where=invoice.type == 'out'))
        for line_id, exento, invoice_id in cursor.fetchall():
            cursor.execute(*line_tax.select(line_tax.id,
                where=line_tax.line == line_id))
            if cursor.fetchone():
                continue
            invoice_line = Line(line_id)
            if exento:
                cursor.execute(*line_tax.insert(
                    columns=[line_tax.line, line_tax.tax],
                    values=[[line_id, iva_venta_exento_id]]))
                key = (invoice_id, iva_venta_exento_id)
                if key not in computed_taxes:
                    computed_taxes[key] = {
                        'invoice': invoice_id,
                        'tax': iva_venta_exento_id,
                        'description': iva_venta_exento.description,
                        'account': iva_venta_exento.invoice_account.id,
                        'base': Decimal('0.0'),
                        'amount': Decimal('0.0'),
                        'manual': False,
                        }
                computed_taxes[key]['base'] += invoice_line.amount
            else:
                cursor.execute(*line_tax.insert(
                    columns=[line_tax.line, line_tax.tax],
                    values=[[line_id, iva_venta_no_gravado_id]]))
                key = (invoice_id, iva_venta_no_gravado_id)
                if key not in computed_taxes:
                    computed_taxes[key] = {
                        'invoice': invoice_id,
                        'tax': iva_venta_no_gravado_id,
                        'description': iva_venta_no_gravado.description,
                        'account': iva_venta_no_gravado.invoice_account.id,
                        'base': Decimal('0.0'),
                        'amount': Decimal('0.0'),
                        'manual': False,
                        }
                computed_taxes[key]['base'] += invoice_line.amount

        cursor.execute(*line.join(invoice,
            condition=line.invoice == invoice.id
            ).select(line.id, line.pyafipws_exento, line.invoice,
            where=invoice.type == 'in'))
        for line_id, exento, invoice_id in cursor.fetchall():
            cursor.execute(*line_tax.select(line_tax.id,
                where=line_tax.line == line_id))
            if cursor.fetchone():
                continue
            invoice_line = Line(line_id)
            if exento:
                cursor.execute(*line_tax.insert(
                    columns=[line_tax.line, line_tax.tax],
                    values=[[line_id, iva_compra_exento_id]]))
                key = (invoice_id, iva_compra_exento_id)
                if key not in computed_taxes:
                    computed_taxes[key] = {
                        'invoice': invoice_id,
                        'tax': iva_compra_exento_id,
                        'description': iva_compra_exento.description,
                        'account': iva_compra_exento.invoice_account.id,
                        'base': Decimal('0.0'),
                        'amount': Decimal('0.0'),
                        'manual': False,
                        }
                computed_taxes[key]['base'] += invoice_line.amount
            else:
                cursor.execute(*line_tax.insert(
                    columns=[line_tax.line, line_tax.tax],
                    values=[[line_id, iva_compra_no_gravado_id]]))
                key = (invoice_id, iva_compra_no_gravado_id)
                if key not in computed_taxes:
                    computed_taxes[key] = {
                        'invoice': invoice_id,
                        'tax': iva_compra_no_gravado_id,
                        'description': iva_compra_no_gravado.description,
                        'account': iva_compra_no_gravado.invoice_account.id,
                        'base': Decimal('0.0'),
                        'amount': Decimal('0.0'),
                        'manual': False,
                        }
                computed_taxes[key]['base'] += invoice_line.amount

        if computed_taxes:
            cursor.execute(*invoice_tax.insert(
                columns=[invoice_tax.invoice, invoice_tax.tax,
                    invoice_tax.description, invoice_tax.account,
                    invoice_tax.base, invoice_tax.amount, invoice_tax.manual],
                values=[[v['invoice'], v['tax'], v['description'],
                    v['account'], v['base'], v['amount'], v['manual']]
                    for v in computed_taxes.values()]))
        return True


class Invoice(metaclass=PoolMeta):
    __name__ = 'account.invoice'

    _states = {'readonly': Eval('state') != 'draft'}

    pos = fields.Many2One('account.pos', 'Point of Sale',
        domain=[('company', '=', Eval('company'))],
        states={
            'required': And(Eval('type') == 'out', Eval('state') != 'draft'),
            'invisible': Eval('type') == 'in',
            'readonly': Eval('state') != 'draft',
            })
    invoice_type = fields.Many2One('account.pos.sequence', 'Comprobante',
        domain=[
            ('pos', '=', Eval('pos')),
            ('invoice_type', 'in',
                If(Eval('total_amount', -1) >= 0,
                    ['1', '2', '4', '5', '6', '7', '9', '11', '12', '15',
                        '19', '20', '201', '202', '206', '207', '211', '212'],
                    ['3', '8', '13', '21', '203', '208', '213']),
                )],
        states={
            'required': And(Eval('type') == 'out', Eval('state') != 'draft'),
            'invisible': Eval('type') == 'in',
            'readonly': Eval('state') != 'draft',
            })
    invoice_type_tree = fields.Function(fields.Selection(INVOICE_TYPE_POS,
        'Tipo comprobante'), 'get_comprobante', searcher='search_comprobante')
    pyafipws_concept = fields.Selection([
        ('1', '1-Productos'),
        ('2', '2-Servicios'),
        ('3', '3-Productos y Servicios'),
        ('4', '4-Otros (exportación)'),
        ('', ''),
        ], 'Concepto',
        states={
            #'required': Eval('_parent_pos', {}).get(
            #    'pos_type') == 'electronic',
            'readonly': Eval('state') != 'draft',
            })
    pyafipws_billing_start_date = fields.Date('Fecha Desde',
        states={
            'required': Eval('pyafipws_concept').in_(['2', '3']),
            'readonly': Eval('state') != 'draft',
            },
        help='Seleccionar fecha de fin de servicios - Sólo servicios')
    pyafipws_billing_end_date = fields.Date('Fecha Hasta',
        states={
            'required': Eval('pyafipws_concept').in_(['2', '3']),
            'readonly': Eval('state') != 'draft',
            },
        help='Seleccionar fecha de inicio de servicios - Sólo servicios')
    pyafipws_transfer_mode = fields.Selection([
        ('SCA', 'Sistema de Circulación Abierta'),
        ('ADC', 'Agente de Depósito Colectivo'),
        ('', ''),
        ], 'Transferencia',
        states={
            'readonly': Eval('state') != 'draft',
            })
    pyafipws_cae = fields.Char('CAE', size=14, readonly=True,
        help='Código de Autorización Electrónico, devuelto por AFIP')
    pyafipws_cae_due_date = fields.Date('Vencimiento CAE', readonly=True,
        help='Fecha tope para verificar CAE, devuelto por AFIP')
    pyafipws_barcode = fields.Char('Codigo de Barras', size=42,
        help='Código de barras para usar en la impresión', readonly=True,)
    pyafipws_number = fields.Char('Número', size=13, readonly=True,
        help='Número de factura informado a la AFIP')
    transactions = fields.One2Many('account_invoice_ar.afip_transaction',
        'invoice', 'Transacciones', readonly=True)
    tipo_comprobante = fields.Selection(TIPO_COMPROBANTE, 'Comprobante',
        states={
            'invisible': Eval('type') == 'out',
            'readonly': Eval('state') != 'draft',
            })
    tipo_comprobante_string = tipo_comprobante.translated('tipo_comprobante')
    pyafipws_incoterms = fields.Selection(INCOTERMS, 'Incoterms')
    pyafipws_licenses = fields.One2Many('account.invoice.export.license',
        'invoice', 'Export Licenses')
    ref_pos_number = fields.Function(fields.Char('POS Number', size=5,
        states={
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
    pos_pos_daily_report = fields.Function(fields.Boolean("POS Daily Report"),
        'on_change_with_pos_pos_daily_report')
    ref_number_from = fields.Char('From number', size=13,
        states={
            'required': Eval('pos_pos_daily_report', False),
            'invisible': ~Eval('pos_pos_daily_report', False),
            'readonly': Eval('state') != 'draft',
            })
    ref_number_to = fields.Char('To number', size=13,
        states={
            'required': Eval('pos_pos_daily_report', False),
            'invisible': ~Eval('pos_pos_daily_report', False),
            'readonly': Eval('state') != 'draft',
            })
    party_iva_condition = fields.Selection('get_party_iva_condition',
        'Condición ante IVA', states=_states)
    party_iva_condition_string = party_iva_condition.translated(
        'party_iva_condition')
    pyafipws_cbu = fields.Many2One('bank.account', 'CBU del Emisor',
        domain=[
            ('owners', '=', Eval('company_party')),
            ('numbers.type', '=', 'cbu'),
            ],
        context={
            'owners': Eval('company_party'),
            'numbers.type': 'cbu',
            },
        states=_states, depends={'company_party'})
    pyafipws_anulacion = fields.Boolean('FCE MiPyme anulación',
        states=_states)
    currency_rate = fields.Numeric('Currency rate', digits=(12, 6),
        states=_states)
    pyafipws_imp_neto = fields.Function(fields.Numeric('Gravado',
        digits=(12, 2)), 'on_change_with_pyafipws_imp_neto')
    pyafipws_imp_tot_conc = fields.Function(fields.Numeric('No Gravado',
        digits=(12, 2)), 'on_change_with_pyafipws_imp_tot_conc')
    pyafipws_imp_op_ex = fields.Function(fields.Numeric('Exento',
        digits=(12, 2)), 'on_change_with_pyafipws_imp_op_ex')
    pyafipws_imp_iva = fields.Function(fields.Numeric('Imp. IVA',
        digits=(12, 2)), 'on_change_with_pyafipws_imp_iva')
    pyafipws_imp_trib = fields.Function(fields.Numeric('Imp. Tributo',
        digits=(12, 2)), 'on_change_with_pyafipws_imp_trib')
    pyafipws_cmp_asoc = fields.Many2Many('account.invoice-cmp.asoc',
        'invoice', 'cmp_asoc', 'Comprobantes asociados',
        domain=[
            ('company', '=', Eval('company', -1)),
            ('type', '=', 'out'),
            ['OR',
                ('state', 'in', ['posted', 'paid']),
                ('id', 'in', Eval('pyafipws_cmp_asoc')),
                ],
            ],
        states=_states)
    pyafipws_cmp_asoc_desde = fields.Date('Período desde',
        states=_states)
    pyafipws_cmp_asoc_hasta = fields.Date('Período hasta',
        states=_states)

    del _states

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.reference.states.update({
            'readonly': Eval('type') == 'in',
            })
        cls.number.states.update({
            'invisible': And(
                Bool(Eval('pos_pos_daily_report', False)),
                Eval('state', 'draft').in_([
                    'draft', 'validated', 'cancelled']))
            })
        cls.number.depends = {'pos_pos_daily_report', 'state'}
        t = cls.__table__()
        #cls._sql_indexes.update({
            #Index(t, (t.pyafipws_concept, Index.Equality())),
            #Index(t, (t.tipo_comprobante, Index.Equality())),
            #})

    @classmethod
    def __register__(cls, module_name):
        super().__register__(module_name)
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

    @staticmethod
    def default_party_iva_condition():
        return ''

    @staticmethod
    def default_pyafipws_anulacion():
        return False

    @staticmethod
    def default_pyafipws_imp_neto():
        return _ZERO

    @staticmethod
    def default_pyafipws_imp_tot_conc():
        return _ZERO

    @staticmethod
    def default_pyafipws_imp_op_ex():
        return _ZERO

    @staticmethod
    def default_pyafipws_imp_iva():
        return _ZERO

    @staticmethod
    def default_pyafipws_imp_trib():
        return _ZERO

    @staticmethod
    def default_pyafipws_transfer_mode():
        return 'SCA'

    def on_change_party(self):
        super().on_change_party()
        if self.party and self.party.iva_condition:
            self.party_iva_condition = self.party.iva_condition

    @fields.depends('currency')
    def on_change_currency(self):
        if self.currency:
            self.currency_rate = self.currency.rate

    @fields.depends('company', 'untaxed_amount', 'lines')
    def on_change_with_pyafipws_imp_neto(self, name=None):
        imp_neto = _ZERO
        if (self.company and self.company.party.iva_condition
                in ('exento', 'monotributo') and self.untaxed_amount):
            return abs(self.untaxed_amount)
        for line in self.lines:
            for tax in line.taxes:
                if tax.group.afip_kind == 'gravado':
                    imp_neto += line.amount
        return abs(imp_neto)

    @fields.depends('company', 'untaxed_amount', 'lines')
    def on_change_with_pyafipws_imp_tot_conc(self, name=None):
        imp_tot_conc = _ZERO
        if (self.company and self.company.party.iva_condition
                in ('exento', 'monotributo')):
            return imp_tot_conc
        for line in self.lines:
            for tax in line.taxes:
                if tax.group.afip_kind == 'no_gravado':
                    imp_tot_conc += line.amount
        return abs(imp_tot_conc)

    @fields.depends('company', 'untaxed_amount', 'lines')
    def on_change_with_pyafipws_imp_op_ex(self, name=None):
        imp_op_ex = _ZERO
        if (self.company and self.company.party.iva_condition
                in ('exento', 'monotributo')):
            return imp_op_ex
        for line in self.lines:
            for tax in line.taxes:
                if tax.group.afip_kind == 'exento':
                    imp_op_ex += line.amount
        return abs(imp_op_ex)

    @fields.depends('taxes', 'lines')
    def on_change_with_pyafipws_imp_trib(self, name=None):
        imp_trib = _ZERO
        for tax_line in self.taxes:
            if (tax_line.tax and tax_line.tax.group.afip_kind not
                    in ('gravado', 'no_gravado', 'exento')):
                imp_trib += tax_line.amount
        return abs(imp_trib)

    @fields.depends('taxes', 'lines')
    def on_change_with_pyafipws_imp_iva(self, name=None):
        imp_iva = _ZERO
        for tax_line in self.taxes:
            if tax_line.tax and tax_line.tax.group.afip_kind == 'gravado':
                imp_iva += tax_line.amount
        return abs(imp_iva)

    @fields.depends('pos')
    def on_change_with_pos_pos_daily_report(self, name=None):
        if self.pos:
            return self.pos.pos_daily_report

    def get_pyafipws_cbu(self):
        "Return the cbu to send afip"
        for bank_account in self.company.party.bank_accounts:
            if bank_account.pyafipws_cbu:
                return bank_account.id

    @fields.depends('company', 'type')
    def on_change_with_pyafipws_cbu(self, name=None):
        if self.company and self.type == 'out':
            return self.get_pyafipws_cbu()

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
        default['reference'] = None
        default['tipo_comprobante'] = None
        return super().copy(invoices, default=default)

    @classmethod
    def validate(cls, invoices):
        super().validate(invoices)
        for invoice in invoices:
            invoice.check_unique_daily_report()

    @classmethod
    def get_party_iva_condition(cls):
        Party = Pool().get('party.party')
        return Party.fields_get(['iva_condition'])[
            'iva_condition']['selection']

    def check_unique_daily_report(self):
        if (self.type == 'out' and self.pos and
                self.pos.pos_daily_report is True):
            if int(self.ref_number_from) > int(self.ref_number_to):
                raise UserError(gettext(
                    'account_invoice_ar.msg_invalid_ref_from_to'))
            invoices = self.search([
                ('id', '!=', self.id),
                ('type', '=', self.type),
                ('pos', '=', self.pos),
                ('invoice_type', '=', self.invoice_type),
                ('state', '!=', 'cancelled'),
                ])
            for invoice in invoices:
                if (invoice.ref_number_to is None or
                        invoice.ref_number_from is None):
                    continue
                ref_number_from = int(invoice.ref_number_from)
                ref_number_to = int(invoice.ref_number_to)
                if ((int(self.ref_number_from) >= ref_number_from and
                     int(self.ref_number_from) <= ref_number_to) or
                    (int(self.ref_number_to) >= ref_number_from and
                     int(self.ref_number_to) <= ref_number_to)):
                    raise UserError(gettext(
                        'account_invoice_ar.msg_reference_unique'))

    @classmethod
    def view_attributes(cls):
        return super().view_attributes() + [
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
            raise UserError(gettext(
                'account_invoice_ar.msg_invalid_ref_number',
                ref_value=value))
        reference = None
        for invoice in invoices:
            if value and invoice.type == 'in':
                if name == 'ref_pos_number':
                    reference = '%05d-%08d' % (int(value or 0),
                        int(invoice.ref_voucher_number or 0))
                elif name == 'ref_voucher_number':
                    reference = '%05d-%08d' % (
                        int(invoice.ref_pos_number or 0), int(value or 0))
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
            invoice.check_vat_existance()
        super().validate_invoice(invoices)

    def check_invoice_type(self):
        if not self.company.party.iva_condition:
            raise UserError(gettext(
                'account_invoice_ar.msg_missing_company_iva_condition',
                company=self.company.rec_name))
        if not self.party.iva_condition:
            raise UserError(gettext(
                'account_invoice_ar.msg_missing_party_iva_condition',
                party=self.party.rec_name))
        if not self.invoice_type:
            raise UserError(gettext(
                'account_invoice_ar.msg_not_invoice_type'))
        if not self.get_tax_identifier():
            raise UserError(gettext(
                'account_invoice_ar.msg_miss_tax_identifier'))
        if (self.get_tax_identifier() and
                not self.company.party.tax_identifier.type == 'ar_cuit'):
            raise UserError(gettext(
                'account_invoice_ar.msg_miss_tax_identifier'))

    def pre_validate_fields(self):
        if not self.reference:
            raise UserError(gettext(
                'account_invoice_ar.msg_invoice_missing_reference'))
        if not self.tipo_comprobante:
            raise UserError(gettext(
                'account_invoice_ar.msg_not_invoice_type'))

    def check_vat_existance(self):
        for t in self.taxes:
            if t.tax and t.tax.group:
                if t.tax.group.code == 'IVA':
                    return
        raise UserError(gettext(
            'account_invoice_ar.msg_vat_not_existance',
            invoice=self.rec_name))

    def _similar_domain(self, delay=None):
        # Ignore cancelled invoices when checking similarity
        domain = super()._similar_domain(delay=None)
        domain.append(('state', '!=', 'cancelled'))
        return domain

    @fields.depends('party', 'tipo_comprobante', 'type', 'reference')
    def on_change_reference(self):
        if self.type == 'in':
            invoice = self.search([
                ('id', '!=', self.id),
                ('type', '=', self.type),
                ('party', '=', self.party.id),
                ('tipo_comprobante', '=', self.tipo_comprobante),
                ('reference', '=', self.reference),
                ('state', '!=', 'cancelled'),
                ])
            if len(invoice) > 0:
                raise UserError(gettext(
                    'account_invoice_ar.msg_reference_unique'))

    @fields.depends('pos', 'party', 'type', 'company')
    def on_change_pos(self):
        self.ref_number_from = None
        self.ref_number_to = None

    @fields.depends('pos', 'party', 'lines', 'company', 'total_amount', 'type')
    def on_change_with_invoice_type(self, name=None):
        return self._set_invoice_type_sequence()

    @classmethod
    def _tax_identifier_types(cls):
        types = super()._tax_identifier_types()
        types.append('ar_cuit')
        return types

    def _set_invoice_type_sequence(self):
        '''
        Set invoice type field.
        require: pos field must be set first.
        '''
        pool = Pool()
        PosSequence = pool.get('account.pos.sequence')

        if not self.pos or not self.party:
            return None

        company_iva = (self.company_party and
            self.company_party.iva_condition or None)
        client_iva = self.party and self.party.iva_condition or None
        credit_note = False
        fce = False
        total_amount = self.total_amount or Decimal('0')
        if total_amount < 0:
            credit_note = True

        if company_iva == 'responsable_inscripto':
            if not client_iva:
                return None
            if client_iva in ('responsable_inscripto', 'monotributo'):
                kind = 'A'
            elif client_iva == 'cliente_exterior':
                kind = 'E'
            else:
                kind = 'B'
        else:
            if client_iva == 'cliente_exterior':
                kind = 'E'
            else:
                kind = 'C'

        if (kind != 'E' and self.party.pyafipws_fce and
                abs(total_amount) >= self.party.pyafipws_fce_amount):
            fce = True

        invoice_type, invoice_type_desc = INVOICE_TYPE_AFIP_CODE[
            (self.type, credit_note, kind, fce)
            ]
        sequences = PosSequence.search([
            ('pos', '=', self.pos),
            ('invoice_type', '=', invoice_type)
            ])
        if len(sequences) == 0:
            raise UserError(gettext(
                'account_invoice_ar.msg_missing_sequence',
                invoice_type=invoice_type_desc))
        elif len(sequences) > 1:
            raise UserError(gettext(
                'account_invoice_ar.msg_too_many_sequences',
                invoice_type_desc))
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
            if line.type != 'line':
                continue
            if line.product:
                if line.product.type == 'goods':
                    products['1'] += 1
                if line.product.type == 'service':
                    products['2'] += 1
            else:
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
        if self.pyafipws_concept not in ['2', '3']:
            return
        if hasattr(self, 'invoice_date') and self.invoice_date:
            year = int(self.invoice_date.strftime("%Y"))
            month = int(self.invoice_date.strftime("%m"))
        else:
            today = Pool().get('ir.date').today()
            year = int(today.strftime("%Y"))
            month = int(today.strftime("%m"))
        self.pyafipws_billing_start_date = date(year, month, 1)
        self.pyafipws_billing_end_date = date(year, month,
            monthrange(year, month)[1])

    def _credit(self, **values):
        pool = Pool()
        PosSequence = pool.get('account.pos.sequence')

        credit = super()._credit(**values)
        credit.currency_rate = self.currency_rate
        if self.type == 'in':
            invoice_type, invoice_type_desc = INVOICE_CREDIT_AFIP_CODE[
                str(int(self.tipo_comprobante))
                ]
            credit.tipo_comprobante = invoice_type.rjust(3, '0')
            credit.reference = None
            return credit

        credit.pos = self.pos
        invoice_type, invoice_type_desc = INVOICE_CREDIT_AFIP_CODE[
            (self.invoice_type.invoice_type)
            ]
        sequences = PosSequence.search([
            ('pos', '=', credit.pos),
            ('invoice_type', '=', invoice_type)
            ])
        if len(sequences) == 0:
            raise UserError(gettext(
                'account_invoice_ar.msg_missing_sequence',
                invoice_type=invoice_type_desc))
        elif len(sequences) > 1:
            raise UserError(gettext(
                'account_invoice_ar.msg_too_many_sequences',
                invoice_type_desc))
        credit.invoice_type = sequences[0]

        credit.pyafipws_cmp_asoc = [self.id]
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

        credit.reference = '%s' % self.number
        return credit

    @classmethod
    def credit(cls, invoices, refund=False, **values):
        '''
        Method overridden by account_invoice_ar to handle AFIP rejections
        with Credit Notes
        '''
        new_invoices = [i._credit(**values) for i in invoices]
        cls.save(new_invoices)
        cls.update_taxes(new_invoices)
        if refund:
            try:
                cls.post(new_invoices)
            except Exception as e:
                cls.delete(new_invoices)
                raise e
            for invoice, new_invoice in zip(invoices, new_invoices):
                if invoice.state != 'posted':
                    raise AccessError(
                        gettext('account_invoice'
                            '.msg_invoice_credit_refund_not_posted',
                            invoice=invoice.rec_name))
                invoice.cancel_move = new_invoice.move
            cls.save(invoices)
            cls.cancel(invoices)
        return new_invoices

    @classmethod
    def set_number(cls, invoices):
        '''
        Set number to the invoice
        '''
        pool = Pool()
        Date = pool.get('ir.date')
        Lang = pool.get('ir.lang')
        Sequence = pool.get('ir.sequence')
        today = Date.today()

        def accounting_date(invoice):
            return invoice.accounting_date or invoice.invoice_date or today

        invoices = sorted(invoices, key=accounting_date)
        sequences = set()

        for invoice in invoices:
            # Posted and paid invoices are tested by check_modify so we can
            # not modify tax_identifier nor number
            if invoice.state in {'posted', 'paid'}:
                continue
            if not invoice.tax_identifier:
                invoice.tax_identifier = invoice.get_tax_identifier()
            # Generated invoice may not fill the party tax identifier
            if not invoice.party_tax_identifier:
                invoice.party_tax_identifier = invoice.party.tax_identifier
            # Generated invoice may not fill the party iva_condition
            if not invoice.party_iva_condition and invoice.type == 'out':
                invoice.party_iva_condition = invoice.party.iva_condition

            if invoice.number:
                continue

            if not invoice.invoice_date and invoice.type == 'out':
                invoice.invoice_date = today
            invoice.number, invoice.sequence = invoice.get_next_number()
            if invoice.type == 'out' and invoice.sequence not in sequences:
                date = accounting_date(invoice)
                # Do not need to lock the table
                # because sequence.get_id is sequential
                after_invoices = cls.search([
                    ('type', '=', 'out'),
                    ('sequence', '=', invoice.sequence),
                    ['OR',
                        ('accounting_date', '>', date),
                        [
                            ('accounting_date', '=', None),
                            ('invoice_date', '>', date)],
                        ],
                    ], order=[
                        ('accounting_date', 'DESC'),
                        ('invoice_date', 'DESC'),
                        ],
                    limit=1)
                if after_invoices:
                    after_invoice, = after_invoices
                    raise InvoiceNumberError(
                        gettext('account_invoice.msg_invoice_number_after',
                            invoice=invoice.rec_name,
                            sequence=Sequence(invoice.sequence).rec_name,
                            date=Lang.get().strftime(date),
                            after_invoice=after_invoice.rec_name))
                sequences.add(invoice.sequence)
        cls.save(invoices)

    def get_next_number(self, pattern=None):
        if self.type == 'out':
            sequence = self.invoice_type.invoice_sequence
            if not sequence:
                raise UserError(gettext(
                    'account_invoice_ar.msg_missing_sequence',
                    self.invoice_type.rec_name))
            accounting_date = self.accounting_date or self.invoice_date
            with Transaction().set_context(date=accounting_date):
                number = sequence.get()
                number = '%05d-%08d' % (self.pos.number, int(number))
                return number, sequence.id
        return super().get_next_number(pattern)

    def get_move(self):
        with Transaction().set_context(currency_rate=self.currency_rate):
            return super().get_move()

    def _get_move_line(self, date, amount):
        line = super()._get_move_line(date, amount)
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
        Pos = pool.get('account.pos')
        Date = pool.get('ir.date')

        draft_invoices = [i for i in invoices if i.state == 'draft']
        if draft_invoices:
            cls.validate_invoice(draft_invoices)

        invoices_wsfe_done = []
        invoices_wsfe_to_recover = []
        invoices_wsfe_batch = {}
        point_of_sales = Pos.search([
            ('pos_type', '=', 'electronic')
            ])
        for pos in point_of_sales:
            pos_number = str(pos.number)
            invoices_wsfe_batch[pos_number] = {}
            for pos_sequence in pos.pos_sequences:
                invoices_wsfe_batch[pos_number][pos_sequence.invoice_type] = []
        invoices_wsfe_non_batch = []

        invoices_in = [i for i in invoices if i.type == 'in']
        invoices_out = [i for i in invoices if i.type == 'out']

        invoices_to_process = invoices_out.copy()

        for invoice in invoices_out:
            invoice.check_invoice_type()
            pos = invoice.pos
            if not pos or pos.pos_type != 'electronic':
                continue
            if (pos.pyafipws_electronic_invoice_service == 'wsfe' and
                    invoice.invoice_type.invoice_type not in [
                    '201', '202', '206', '211', '212', '203', '208', '213']):
                if invoice.number and invoice.pyafipws_cae:
                    invoices_wsfe_done.append(invoice)
                elif invoice.number:
                    invoices_wsfe_to_recover.append(invoice)
                else:
                    invoices_wsfe_batch[str(pos.number)][
                        invoice.invoice_type.invoice_type].append(invoice)
            else:
                if invoice.number and invoice.pyafipws_cae:
                    invoices_wsfe_done.append(invoice)
                else:
                    invoices_wsfe_non_batch.append(invoice)
            invoices_to_process.remove(invoice)

        for invoice in invoices_to_process:
            pos = invoice.pos
            if not pos or pos.pos_type != 'fiscal_printer':
                continue
            if pos.pos_daily_report:
                if not invoice.invoice_date:
                    invoice.invoice_date = Date.today()
                invoice.number = '%05d-%08d:%d' % \
                    (pos.number, int(invoice.ref_number_from),
                     int(invoice.ref_number_to))
            else:
                #TODO: Implement fiscal printer integration
                cls.fiscal_printer_invoice_post()

        invoices_wsfe_recovered = cls.consultar_and_recover(
            invoices_wsfe_to_recover)
        failed_recover = [i for i in invoices_wsfe_recovered if not i.number]
        if failed_recover:
            raise UserError(gettext(
                    'account_invoice_ar.msg_reprocesar_invoice_dif'))

        error_afip, error_pre_afip = [], []

        for i in invoices_wsfe_non_batch:
            (approved, pre_rejected, rejected) = cls.post_ws(i)
            if rejected:
                error_afip.append(rejected)
            if pre_rejected:
                error_pre_afip.append(pre_rejected)

        for pos, value_dict in list(invoices_wsfe_batch.items()):
            for key, invoices_by_type in list(value_dict.items()):
                (approved, pre_rejected, rejected) = cls.post_ws_batch(
                        [i for i in invoices_by_type if not i.number])
                if rejected:
                    error_afip.append(rejected)
                if pre_rejected:
                    error_pre_afip.append(pre_rejected)

        if invoices_wsfe_done:
            invoices_to_process.extend(invoices_wsfe_done)
        if invoices_wsfe_recovered:
            invoices_to_process.extend(invoices_wsfe_recovered)
        if invoices_in:
            invoices_to_process.extend(invoices_in)

        cls.save(invoices)
        super().post(invoices_to_process)
        Transaction().commit()

        if error_afip:
            raise UserError(gettext(
                'account_invoice_ar.msg_rejected_invoices',
                invoices=','.join([str(i.id) for i in error_afip]),
                msg=','.join([i.transactions[-1].pyafipws_message
                    for i in error_afip if i.transactions])))

        if error_pre_afip:
            raise UserError(gettext(
                'account_invoice_ar.msg_rejected_invoices',
                invoices=','.join([str(i.id) for i in error_pre_afip]),
                msg=''))

    @classmethod
    def consultar_and_recover(cls, invoices):
        for invoice in invoices:
            ws = cls.get_ws_afip(invoice=invoice)
            if not invoice.invoice_date:
                raise UserError(gettext(
                    'account_invoice_ar.msg_missing_invoice_date'))
            ws.Reprocesar = True
            (ws, error) = invoice.create_pyafipws_invoice(ws)
            cbte_nro = int(invoice.number[-8:])
            cae = ws.CompConsultar(invoice.invoice_type.invoice_type,
                invoice.pos.number, cbte_nro, reproceso=True)
            if cae and ws.EmisionTipo == 'CAE':
                # la factura se recupera y puede pasar a estado posted
                logger.info('se ha reprocesado invoice %s', invoice.id)
                invoice.save_afip_tr(ws, msg='Reprocesar=S')
                tipo_cbte = invoice.invoice_type.invoice_type
                punto_vta = invoice.pos.number
                vto = ws.Vencimiento
                cae_due = ''.join([c for c in str(vto)
                        if c.isdigit()])
                bars = ''.join([str(ws.Cuit), '%03d' % int(tipo_cbte),
                        '%05d' % int(punto_vta), str(cae), cae_due])
                bars += invoice.pyafipws_verification_digit_modulo10(bars)
                pyafipws_cae_due_date = vto or None
                if '-' not in vto:
                    pyafipws_cae_due_date = '-'.join(
                        [vto[:4], vto[4:6], vto[6:8]])
                invoice.pyafipws_cae = cae
                invoice.pyafipws_barcode = bars
                invoice.pyafipws_cae_due_date = datetime.strptime(
                    pyafipws_cae_due_date, "%Y-%m-%d").date()

                # commit()
                cls.save([invoice])
                Transaction().commit()
            else:
                invoice.number = None
                invoice.invoice_date = None
                # commit()
                cls.save([invoice])
                Transaction().commit()
                logger.error('diferencias entre el comprobante %s '
                    'que tiene AFIP y el de tryton.', invoice.id)
        return invoices

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
            raise UserError(gettext(
                'account_invoice_ar.msg_webservice_unknown'))

        (company, ta) = cls.authenticate_afip(service=service)
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
            raise UserError(gettext(
                'account_invoice_ar.msg_webservice_not_supported',
                service=service))

        ws = cls.conect_afip(ws, WSDL, company.party.vat_number, ta)
        ws.Reprocesar = False
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
            raise UserError(gettext(
                'account_invoice_ar.msg_company_not_defined'))
        company = Company(company_id)
        # authenticate against AFIP:
        ta = company.pyafipws_authenticate(service=service)
        return (company, ta)

    @classmethod
    def conect_afip(cls, ws, wsdl, vat_number, ta):
        '''
        Connect to WSAA webservice
        '''
        pool = Pool()
        Company = pool.get('company.company')
        cache = Company.get_cache_dir()
        ws.LanzarExcepciones = True
        ws.SetTicketAcceso(ta)
        ws.Cuit = vat_number
        try:
            ws.Conectar(wsdl=wsdl, cache=cache, cacert=True)
        except Exception as e:
            msg = ws.Excepcion + ' ' + str(e)
            logger.error('WSAA connecting to afip: %s' % msg)
            raise UserError(gettext(
                'account_invoice_ar.msg_wsaa_error', msg=msg))
        return ws

    @classmethod
    def post_ws(cls, invoice):
        '''
        Post non batch invoice.
        '''
        pool = Pool()
        Date = pool.get('ir.date')

        if not invoice:
            return (None, None, None)

        ws = cls.get_ws_afip(invoice)
        pre_approved = None
        approved = None
        pre_rejected = None
        rejected = None
        error_obtained = False

        if not invoice.invoice_date:
            invoice.invoice_date = Date.today()
        (ws, error) = invoice.create_pyafipws_invoice(ws, batch=False)
        if error is False:
            pre_approved = invoice
        else:
            error_obtained = True
            invoice.invoice_date = None
            pre_rejected = invoice
            logger.error('%s: %s Entidad: %s',
                invoice.invoice_type.invoice_type_string,
                invoice.id, invoice.party.rec_name)

        if pre_approved:
            cls.set_number([invoice])
            (ws, error) = invoice.create_pyafipws_invoice(ws, batch=False)
            (ws, msg) = invoice.request_cae(ws)
            result = invoice.process_afip_result(ws, msg=msg)
            if result == 'A':
                approved = invoice
            else:
                error_obtained = True
                if result != 'R':
                    invoice.number = None
                    invoice.invoice_date = None
                rejected = invoice
                logger.error(
                    '%s: %s Entidad: %s\n'
                    'XmlRequest: %s\nXmlResponse: %s\n',
                    rejected.invoice_type.invoice_type_string,
                    rejected.id, rejected.party.rec_name,
                    repr(ws.XmlRequest), repr(ws.XmlResponse))

            # commit()
            cls.save([invoice])
            Transaction().commit()
            if approved:
                super().post([approved])
                Transaction().commit()

        if error_obtained and rejected:
            rejected.reset_sequence_from_ws(ws)

        return (approved, pre_rejected, rejected)

    @classmethod
    def post_ws_batch(cls, invoices):
        '''
        Post batch invoices.
        '''
        pool = Pool()
        Date = pool.get('ir.date')

        if invoices == []:
            return ([], [], [])

        ws = cls.get_ws_afip(batch=True)
        reg_x_req = ws.CompTotXRequest()    # cant max. comprobantes
        pre_approved = []
        approved = []
        pre_rejected = None
        rejected = None

        # before set_number, validate some stuff.
        # get only invoices that pass validations.
        # TODO: Add those validations to validate_invoice method.
        for invoice in invoices:
            # TODO: usar try/except
            if not invoice.invoice_date:
                invoice.invoice_date = Date.today()
            (ws, error) = invoice.create_pyafipws_invoice(ws, batch=True)
            if error is False:
                pre_approved.append(invoice)
            else:
                invoice.invoice_date = None
                if pre_rejected is None:
                    pre_rejected = invoice
                logger.error('%s: %s Entidad: %s',
                    invoice.invoice_type.invoice_type_string,
                    invoice.id, invoice.party.rec_name)

        tmp_ = [pre_approved[i:i + reg_x_req] for i in
            range(0, len(pre_approved), reg_x_req)]
        for chunk_invoices in tmp_:
            excepcion = False
            ws.IniciarFacturasX()
            invoices_added_to_ws = []
            error_obtained = False
            cls.set_number(chunk_invoices)
            for invoice in chunk_invoices:
                (ws, error) = invoice.create_pyafipws_invoice(ws, batch=True)
                if error is False:
                    ws.AgregarFacturaX()
                    invoices_added_to_ws.append(invoice)
            # CAESolicitarX
            try:
                cant_solicitadax = ws.CAESolicitarX()
                logger.info('wsfe batch invoices posted: %s' %
                    cant_solicitadax)
            except Exception as e:
                logger.error('CAESolicitarX msg: %s' % str(e))
                excepcion = True

            # Process results:
            cant = 0
            for invoice in invoices_added_to_ws:
                ws.LeerFacturaX(cant)
                cant += 1
                result = 'R' if excepcion else invoice.process_afip_result(ws)
                if result == 'A':
                    approved.append(invoice)
                else:
                    error_obtained = True
                    if result != 'R':
                        invoice.number = None
                        invoice.invoice_date = None
                    if rejected is None:
                        rejected = invoice
                        logger.error(
                            '%s: %s Entidad: %s\n'
                            'XmlRequest: %s\nXmlResponse: %s\n',
                            rejected.invoice_type.invoice_type_string,
                            rejected.id, rejected.party.rec_name,
                            repr(ws.XmlRequest), repr(ws.XmlResponse))
            # commit()
            cls.save(invoices_added_to_ws)
            Transaction().commit()
            if approved:
                super().post(approved)
                Transaction().commit()

            if error_obtained and rejected:
                rejected.reset_sequence_from_ws(ws)

        return (approved, pre_rejected, rejected)

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
            except (TypeError, NameError):  # unicode is a default on python 3
                pass
            text = normalize('NFD', text)
            text = text.encode('ascii', 'ignore')
            text = text.decode("utf-8")
            return str(text)

        # verify pyafipws_concept
        if not self.pyafipws_concept:
            if batch:
                logger.error('missing_pyafipws_concept:field pyafipws_concept '
                    'is missing at invoice "%s"' % self.rec_name)
                return (ws, True)
            raise UserError(gettext(
                'account_invoice_ar.msg_missing_pyafipws_concept'))
        if (self.pyafipws_concept in ['2', '3'] and not
                (self.pyafipws_billing_start_date or
                    self.pyafipws_billing_end_date)):
                if batch:
                    logger.error('missing_pyafipws_billing_date:billing_dates '
                        'fields are missing at invoice "%s"' % self.rec_name)
                    return (ws, True)
                raise UserError(gettext(
                    'account_invoice_ar.msg_missing_pyafipws_billing_date'))
        # get the electronic invoice type, point of sale and service:
        pool = Pool()
        Sequence = pool.get('ir.sequence')
        Date = pool.get('ir.date')
        today = Date.today()

        # get the electronic invoice type, point of sale and service:
        tipo_cbte = self.invoice_type.invoice_type
        punto_vta = self.pos.number
        service = self.pos.pyafipws_electronic_invoice_service

        if service == 'wsfex' and not self.party.vat_number_afip_foreign:
            logger.error('missing_cuit_pais: %s', self.party.rec_name)
            raise UserError(gettext('account_invoice_ar.msg_missing_cuit_pais',
                party=self.party.rec_name))

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
            if service == 'wsfe':
                cbte_nro_afip = ws.CompUltimoAutorizado(tipo_cbte, punto_vta)
            elif service == 'wsmtxca':
                cbte_nro_afip = ws.ConsultarUltimoComprobanteAutorizado(
                    tipo_cbte, punto_vta)
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
                raise UserError(gettext(
                    'account_invoice_ar.msg_invalid_invoice_number',
                    cbte_nro=cbte_nro, cbte_nro_next=cbte_nro_next))

        # invoice number range (from - to) and date:
        cbte_nro = cbt_desde = cbt_hasta = cbte_nro_next

        if self.invoice_date:
            fecha_cbte = self.invoice_date.strftime('%Y-%m-%d')
        else:
            fecha_cbte = today.strftime('%Y-%m-%d')

        if service != 'wsmtxca':
            fecha_cbte = fecha_cbte.replace('-', '')

        # due and billing dates only for concept 'services'
        concepto = tipo_expo = int(self.pyafipws_concept or 0)
        fecha_venc_pago = fecha_serv_desde = fecha_serv_hasta = None
        fecha_pago = None
        if (int(concepto) != 1 or
                self.invoice_type.invoice_type in ('201', '202', '203', '206',
                    '207', '208', '211', '212', '213')):
            payments = []
            if self.payment_term:
                payment_date = self.invoice_date or today
                payments = self.payment_term.compute(self.total_amount,
                    self.currency, payment_date)
            if payments:
                last_payment = max(payments, key=lambda x: x[0])[0]
            elif service == 'wsfe' and ws.Reprocesar:
                last_payment = self.invoice_date
            else:
                last_payment = today
            fecha_venc_pago = last_payment.strftime('%Y-%m-%d')
            if service != 'wsmtxca':
                fecha_venc_pago = fecha_venc_pago.replace('-', '')

            if service == 'wsfex' and self.invoice_type.invoice_type == '19':
                fecha_pago = fecha_venc_pago

            if self.invoice_type.invoice_type in ('202', '203', '207',
                    '208', '212', '213'):
                if not self.pyafipws_anulacion:
                    fecha_venc_pago = None

        if int(concepto) != 1:
            if self.pyafipws_billing_start_date:
                fecha_serv_desde = self.pyafipws_billing_start_date.strftime(
                    '%Y-%m-%d')
                if service != 'wsmtxca':
                    fecha_serv_desde = fecha_serv_desde.replace('-', '')
            if self.pyafipws_billing_end_date:
                fecha_serv_hasta = self.pyafipws_billing_end_date.strftime(
                    '%Y-%m-%d')
                if service != 'wsmtxca':
                    fecha_serv_hasta = fecha_serv_hasta.replace('-', '')

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
        imp_subtotal = str('%.2f' % abs(self.untaxed_amount))  # TODO
        imp_tot_conc = self.pyafipws_imp_tot_conc
        imp_neto = self.pyafipws_imp_neto
        imp_iva = self.pyafipws_imp_iva
        imp_trib = self.pyafipws_imp_trib
        imp_op_ex = self.pyafipws_imp_op_ex

        # currency and rate
        moneda_id = self.currency.afip_code
        if not moneda_id:
            if batch:
                logger.error('missing_currency_afip_code: Invoice: %s, '
                    'currency afip code is not setted.' % self.id)
                return (ws, True)
            raise UserError(gettext(
                'account_invoice_ar.msg_missing_currency_afip_code'))

        if moneda_id != "PES":
            ctz = self.currency_rate
        else:
            if self.company.currency.rate == Decimal('0'):
                if self.party.vat_number_afip_foreign:
                    if batch:
                        logger.error('missing_currency_rate: Invoice: %s, '
                            'rate is not setted.' % self.id)
                        return (ws, True)
                    raise UserError(gettext(
                        'account_invoice_ar.msg_missing_currency_rate'))
                else:
                    ctz = 1
            elif self.company.currency.rate == Decimal('1'):
                ctz = 1 / self.currency.rate
            else:
                ctz = self.company.currency.rate / self.currency.rate
        moneda_ctz = str('%.6f' % ctz)

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
            raise UserError(gettext(
                'account_invoice_ar.msg_missing_pyafipws_incoterms'))

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
                    address.postal_code or '',
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
                idioma_cbte, incoterms_ds, fecha_pago)

        # analyze VAT (IVA) and other taxes (tributo):
        if service in ('wsfe', 'wsmtxca'):
            if (self.invoice_type.invoice_type in ('201', '202', '203',
                    '206', '207', '208', '211', '212', '213')):
                if self.invoice_type.invoice_type in ('201', '206', '211'):
                    self.pyafipws_cbu = (self.pyafipws_cbu or
                        self.get_pyafipws_cbu())
                    if not self.pyafipws_cbu:
                        raise UserError(gettext(
                            'account_invoice_ar.msg_fce_10168_cbu_emisor'))
                    ws.AgregarOpcional(2101,
                        self.pyafipws_cbu.get_cbu_number())  # CBU
                    ws.AgregarOpcional(27, self.pyafipws_transfer_mode)
                    # ws.AgregarOpcional(2102, "tryton")  # alias del cbu
                if self.invoice_type.invoice_type in ('202', '203', '207',
                        '208', '212', '213'):
                    if self.pyafipws_anulacion:
                        ws.AgregarOpcional(22, 'S')
                    else:
                        ws.AgregarOpcional(22, 'N')
            if (self.invoice_type.invoice_type in ('2', '3', '7', '8', '12',
                    '13', '202', '203', '207', '208', '212', '213')):
                if (not self.pyafipws_cmp_asoc and not
                        (self.pyafipws_cmp_asoc_desde and
                        self.pyafipws_cmp_asoc_hasta)):
                    raise UserError(gettext(
                        'account_invoice_ar.msg_missing_cmp_asoc'))
                if (self.pyafipws_cmp_asoc_desde and
                        self.pyafipws_cmp_asoc_hasta):
                    cmp_asoc_desde = self.pyafipws_cmp_asoc_desde.strftime(
                        '%Y%m%d')
                    cmp_asoc_hasta = self.pyafipws_cmp_asoc_hasta.strftime(
                        '%Y%m%d')
                    ws.AgregarPeriodoComprobantesAsociados(cmp_asoc_desde,
                        cmp_asoc_hasta)
                else:
                    for cmp in self.pyafipws_cmp_asoc:
                        cmp_tipo = int(cmp.invoice_type.invoice_type)
                        if cmp_tipo not in INVOICE_ASOC_AFIP_CODE[
                                self.invoice_type.invoice_type]:
                            raise UserError(gettext(
                                'account_invoice_ar.msg_invalid_cmp_asoc'))
                        cmp_nro = int(cmp.number[-8:])
                        cmp_fecha_cbte = cmp.invoice_date.strftime('%Y-%m-%d')
                        if service != 'wsmtxca':
                            cmp_fecha_cbte = cmp_fecha_cbte.replace('-', '')
                        ws.AgregarCmpAsoc(cmp_tipo, punto_vta, cmp_nro,
                            self.company.party.tax_identifier.code,
                            cmp_fecha_cbte)

            for tax_line in self.taxes:
                tax = tax_line.tax
                if not tax.group:
                    if batch:
                        logger.error('tax_without_group: Invoice: %s, tax: %s'
                            % (self.id, tax.name))
                        return (ws, True)
                    raise UserError(gettext(
                        'account_invoice_ar.msg_tax_without_group',
                        tax=tax.name))
                if tax.group.afip_kind == 'gravado':
                    iva_id = tax.iva_code
                    base_imp = ('%.2f' % abs(tax_line.base))
                    importe = ('%.2f' % abs(tax_line.amount))
                    ws.AgregarIva(iva_id, base_imp, importe)
                elif tax.group.afip_kind not in ('no_gravado', 'exento'):
                    tributo_id = tax.group.tribute_id
                    desc = tax.name
                    base_imp = ('%.2f' % abs(tax_line.base))
                    importe = ('%.2f' % abs(tax_line.amount))
                    alic = '%.2f' % (abs(tax_line.amount) /
                        abs(tax_line.base) * 100)
                    # add the other tax detail in the helper
                    ws.AgregarTributo(tributo_id, desc, base_imp, alic,
                        importe)

        # analize line items - invoice detail
        # umeds
        # Parametros. Unidades de Medida, etc.
        # https://code.google.com/p/pyafipws/wiki/WSFEX#WSFEX/
        #     RECEX_Parameter_Tables
        if service in ('wsfex', 'wsmtxca'):
            for line in self.lines:
                if line.type == 'line':
                    if line.product:
                        codigo = line.product.code
                    else:
                        codigo = 0
                    ds = strip_accents(line.description or '-')
                    qty = abs(line.quantity)
                    umed = 7  # FIXME: (7 - unit)
                    precio = line.unit_price
                    importe_total = abs(line.amount)
                    bonif = None  # line.discount
                    #for tax in line.taxes:
                    #    if tax.group.afip_kind == 'gravado':
                    #        iva_id = tax.iva_code
                    #        imp_iva = importe * tax.rate
                    #if service == 'wsmtxca':
                    #    ws.AgregarItem(u_mtx, cod_mtx, codigo, ds, qty, umed,
                    #            precio, bonif, iva_id, imp_iva,
                    #            importe+imp_iva)
                    if service == 'wsfex':
                        ws.AgregarItem(codigo, ds, qty, umed, precio,
                            importe_total, bonif)

            if service == 'wsfex':
                for export_license in self.pyafipws_licenses:
                    ws.AgregarPermiso(
                        export_license.license_id,
                        export_license.afip_country.code)
                if int(tipo_cbte) in (20, 21):
                    for cbteasoc in self.pyafipws_cmp_asoc:
                        cbteasoc_tipo = int(cbteasoc.invoice_type.invoice_type)
                        cbteasoc_nro = int(cbteasoc.number[-8:])
                        ws.AgregarCmpAsoc(cbteasoc_tipo, punto_vta,
                            cbteasoc_nro,
                            self.company.party.tax_identifier.code)
                if not self.lines:
                    codigo = 0
                    ds = '-'
                    qty = 1
                    umed = 7
                    precio = Decimal('0')
                    importe_total = Decimal('0')
                    bonif = None
                    ws.AgregarItem(codigo, ds, qty, umed, precio,
                        importe_total, bonif)
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
                wsfex_id = ws.GetLastID() + 1
                ws.Authorize(wsfex_id)
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
        xml_request = ws.XmlRequest
        if not isinstance(xml_request, str):
            xml_request = xml_request.decode('utf-8')
        xml_response = ws.XmlResponse.decode('utf-8')
        if not isinstance(xml_response, str):
            xml_response = xml_response.decode('utf-8')
        afip_tr = AFIP_Transaction()
        afip_tr.invoice = self
        afip_tr.pyafipws_result = ws.Resultado
        afip_tr.pyafipws_message = message.decode('utf-8')
        afip_tr.pyafipws_xml_request = xml_request
        afip_tr.pyafipws_xml_response = xml_response
        afip_tr.save()
        return afip_tr

    def process_afip_result(self, ws, msg=''):
        '''
        Process CAE and store results
        '''
        afip_tr = self.save_afip_tr(ws, msg)
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
            bars = ''.join([str(ws.Cuit), '%03d' % int(tipo_cbte),
                    '%05d' % int(punto_vta), str(ws.CAE), cae_due])
            bars = bars + self.pyafipws_verification_digit_modulo10(bars)
            pyafipws_cae_due_date = vto or None
            if '-' not in vto:
                pyafipws_cae_due_date = '-'.join([vto[:4], vto[4:6], vto[6:8]])
            self.pyafipws_cae = ws.CAE
            self.pyafipws_barcode = bars
            self.pyafipws_cae_due_date = datetime.strptime(
                pyafipws_cae_due_date, "%Y-%m-%d").date()

            return 'A'

        if afip_tr.pyafipws_message.find('502:') != -1:
            return 'R'

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

    def reset_sequence_from_ws(self, ws):
        '''
        Set next sequence number to be the last cbte_nro_afip + 1.
        '''
        sequence = self.invoice_type.invoice_sequence
        tipo_cbte = self.invoice_type.invoice_type
        punto_vta = self.pos.number
        service = self.pos.pyafipws_electronic_invoice_service

        if service == 'wsfe':
            cbte_nro_afip = ws.CompUltimoAutorizado(tipo_cbte, punto_vta)
        elif service == 'wsmtxca':
            cbte_nro_afip = ws.ConsultarUltimoComprobanteAutorizado(
                tipo_cbte, punto_vta)
        elif service == 'wsfex':
            cbte_nro_afip = ws.GetLastCMP(tipo_cbte, punto_vta)
        else:
            cbte_nro_afip = None

        if cbte_nro_afip is not None:
            sequence.update_sql_sequence(int(cbte_nro_afip) + 1)


class InvoiceExportLicense(ModelSQL, ModelView):
    'Invoice Export License'
    __name__ = 'account.invoice.export.license'

    invoice = fields.Many2One('account.invoice', 'Invoice',
        ondelete='CASCADE', required=True)
    license_id = fields.Char('License Id', required=True)
    afip_country = fields.Many2One('afip.country', 'AFIP Country',
        required=True)

    @classmethod
    def __register__(cls, module_name):
        super().__register__(module_name)
        cursor = Transaction().connection.cursor()
        afip_country = Pool().get('afip.country').__table__()
        table = cls.__table__()

        table_h = cls.__table_handler__(module_name)

        # Migration legacy: country -> afip_country
        if table_h.column_exist('country'):
            cursor.execute(*table.select(table.id, table.country))
            for id, country in cursor.fetchall():
                if country != '':
                    cursor.execute(*afip_country.select(afip_country.id,
                            where=(afip_country.code == country)))
                    row, = cursor_dict(cursor)
                    cursor.execute(*table.update(
                        [table.afip_country], [row['id']],
                        where=(table.id == id)))
            table_h.drop_column('country')


class InvoiceReport(metaclass=PoolMeta):
    __name__ = 'account.invoice'

    @classmethod
    def get_context(cls, records, header, data):
        pool = Pool()
        Invoice = pool.get('account.invoice')

        context = super().get_context(records, header, data)
        invoice = context['record']
        context['company'] = invoice.company
        context['barcode_img'] = cls._get_pyafipws_barcode_img(Invoice,
            invoice)
        context['condicion_iva'] = cls._get_condicion_iva(invoice.company)
        context['iibb_type'] = cls._get_iibb_type(invoice.company)
        context['vat_number'] = cls._get_vat_number(invoice)
        context['tipo_comprobante'] = cls._get_tipo_comprobante(Invoice,
            invoice)
        context['nombre_comprobante'] = cls._get_nombre_comprobante(
            Invoice, invoice)
        context['codigo_comprobante'] = cls._get_codigo_comprobante(
            Invoice, invoice)
        context['condicion_iva_cliente'] = (
            cls._get_condicion_iva_cliente(Invoice, invoice))
        context['vat_number_cliente'] = cls._get_vat_number_cliente(
            Invoice, invoice)
        context['dni_number_cliente'] = cls._get_dni_number_cliente(
            Invoice, invoice)
        context['leyenda_ley_27618'] = cls._get_leyenda_ley_27618(invoice)
        context['get_impuestos'] = cls.get_impuestos
        context['get_line_amount'] = cls.get_line_amount
        context['get_taxes'] = cls.get_taxes
        context['get_subtotal'] = cls.get_subtotal
        context['incluir_reg_transp_fiscal'] = cls.incluir_reg_transp_fiscal(
            invoice)
        context['get_iva_contenido'] = cls.get_iva_contenido
        context['discrimina_impuestos'] = cls.discrimina_impuestos(invoice)
        context['qr'] = cls.get_qr_img(Invoice, invoice)
        return context

    @classmethod
    def get_line_amount(cls, line_amount, line_taxes,
            invoice_type=None, tax_date=None):

        def is_credit_note(invoice_type):
            if (invoice_type and invoice_type.invoice_type in
                    ('3', '8', '13', '21', '203', '208', '213')):
                return True
            return False

        if is_credit_note(invoice_type):
            line_amount = abs(line_amount)
        Tax = Pool().get('account.tax')
        line_taxes = cls.get_line_taxes(line_taxes)
        for line_tax in line_taxes:
            values, = Tax.compute([line_tax.tax], line_amount, 1, tax_date)
            line_amount = values['amount'] + values['base']
        return line_amount

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
                if tax.tax.group.afip_kind == 'gravado':
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
            for tax in taxes:
                if (tax.tax.group.afip_kind not
                        in ('no_gravado', 'exento')):
                    res.append(tax)
        elif invoice_type_string == 'B':
            for tax in taxes:
                if (tax.tax.group.afip_kind not
                        in ('gravado', 'no_gravado', 'exento')):
                    res.append(tax)
        return res

    @classmethod
    def incluir_reg_transp_fiscal(cls, invoice):
        # Invoice type: B
        if invoice.invoice_type and invoice.invoice_type.invoice_type in [
                '6', '7', '8', '9', '10', '206', '207', '208']:
            return True
        return False

    @classmethod
    def get_iva_contenido(cls, invoice):
        tax_amount = Decimal('0')
        for tax in invoice.taxes:
            if tax.tax.group.kind == 'sale' and tax.tax.group.code == 'IVA':
                tax_amount += abs(tax.amount)
        return tax_amount

    @classmethod
    def discrimina_impuestos(cls, invoice):
        invoice_type_string = ''
        if invoice.invoice_type:
            invoice_type_string = invoice.invoice_type.invoice_type_string[-1]

        if invoice_type_string == 'A':
            return True
        return False

    @classmethod
    def _get_condicion_iva_cliente(cls, Invoice, invoice):
        if not invoice.party_iva_condition:
            return invoice.party.iva_condition_string
        return invoice.party_iva_condition_string

    @classmethod
    def _get_vat_number_cliente(cls, Invoice, invoice):
        value = ''
        if invoice.party_tax_identifier:
            value = invoice.party_tax_identifier.code
        elif invoice.party.vat_number:
            value = invoice.party.vat_number
        return cuit.format(value)

    @classmethod
    def _get_dni_number_cliente(cls, Invoice, invoice):
        value = ''
        for identifier in invoice.party.identifiers:
            if identifier.type == 'ar_dni':
                value = identifier.code
        return value

    @classmethod
    def _get_leyenda_ley_27618(cls, invoice):
        if invoice.company.party.iva_condition == 'responsable_inscripto' \
                and invoice.party.iva_condition == 'monotributo':
            return 'El crédito fiscal discriminado en el presente ' \
                'comprobante, sólo podrá ser computado a efectos del ' \
                'Régimen de Sostenimiento e Inclusión Fiscal para Pequeños ' \
                ' Contribuyentes de la Ley Nº 27.618'
        return ''

    @classmethod
    def _get_tipo_comprobante(cls, Invoice, invoice):
        if invoice.invoice_type:
            return invoice.invoice_type.invoice_type_string[-1]
        else:
            return ''

    @classmethod
    def _get_nombre_comprobante(cls, Invoice, invoice):
        if invoice.invoice_type:
            return invoice.invoice_type.rec_name
        else:
            return ''

    @classmethod
    def _get_codigo_comprobante(cls, Invoice, invoice):
        if invoice.invoice_type:
            return invoice.invoice_type.invoice_type
        else:
            return ''

    @classmethod
    def _get_vat_number(cls, invoice):
        if invoice.tax_identifier:
            value = invoice.tax_identifier.code
        else:
            value = invoice.company.party.vat_number
        return cuit.format(value)

    @classmethod
    def _get_condicion_iva(cls, company):
        return company.party.iva_condition_string

    @classmethod
    def _get_iibb_type(cls, company):
        if company.party.iibb_condition and company.party.iibb_number:
            if company.party.iibb_condition.lower() == 'cm':
                return '%s  %s-%s' % (
                        company.party.iibb_condition.upper(),
                        company.party.iibb_number[:3],
                        company.party.vat_number)
            else:
                return '%s %s' % (
                        company.party.iibb_condition.upper(),
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
        image = output.getvalue()
        output.close()
        return image

    @classmethod
    def get_qr_img(cls, Invoice, invoice):
        'Generate the required qr'
        'https://www.afip.gob.ar/fe/qr/especificaciones.asp'
        image = None
        if (invoice.pos and invoice.pos.pos_type in
                ('electronic', 'fiscal_printer')
                and invoice.type == 'out'
                and invoice.state in ('posted', 'paid')
                and invoice.pyafipws_cae):
            ver = 1
            fecha = invoice.invoice_date.strftime("%Y-%m-%d")
            cuit = int(cls._get_vat_number(invoice).replace("-", ""))
            pto_vta = invoice.pos.number
            tipo_cmp = int(cls._get_codigo_comprobante(Invoice, invoice))
            nro_cmp = int(invoice.number[6:])
            importe = float(invoice.total_amount)
            moneda = invoice.currency.afip_code
            ctz = cls._get_ctz(invoice)
            tipo_doc, nro_doc = cls._obtiene_tipo_nro_doc(invoice)
            tipo_doc_rec = tipo_doc
            nro_doc_rec = int(nro_doc)
            tipo_cod_aut = "E"
            cod_aut = invoice.pyafipws_cae

            PyQR_ = pyqr.PyQR()
            PyQR_.CrearArchivo()
            PyQR_.GenerarImagen(ver, fecha, cuit, pto_vta, tipo_cmp,
                nro_cmp, importe, moneda, ctz, tipo_doc_rec, nro_doc_rec,
                tipo_cod_aut, cod_aut)

            with open(PyQR_.Archivo, 'rb') as archivoQR:
                output = BytesIO(archivoQR.read())
                image = (output.getvalue(), 'image/png')
                output.close()
        return image

    @classmethod
    def _get_ctz(cls, invoice):
        # currency and rate
        moneda_id = invoice.currency.afip_code
        if not moneda_id:
            raise UserError(gettext(
                    'account_invoice_ar.msg_missing_currency_afip_code'))

        if moneda_id != "PES":
            ctz = invoice.currency_rate
        else:
            if invoice.company.currency.rate == Decimal('0'):
                if invoice.party.vat_number_afip_foreign:
                    raise UserError(gettext(
                            'account_invoice_ar.msg_missing_currency_rate'))
                else:
                    ctz = 1
            elif invoice.company.currency.rate == Decimal('1'):
                ctz = 1 / invoice.currency.rate
            else:
                ctz = invoice.company.currency.rate / invoice.currency.rate
        moneda_ctz = "{:.{}f}".format(ctz, 6)
        return moneda_ctz

    @classmethod
    def _obtiene_tipo_nro_doc(cls, invoice):
        nro_doc = None
        tipo_doc = None
        if invoice.party.vat_number:
            nro_doc = invoice.party.vat_number
            tipo_doc = 80  # CUIT
        else:
            for identifier in invoice.party.identifiers:
                if identifier.type == 'ar_dni':
                    nro_doc = identifier.code
                    tipo_doc = 96
            if nro_doc is None:
                nro_doc = '0'  # only 'consumidor final'
                tipo_doc = 99
        return tipo_doc, nro_doc


class CreditInvoiceStart(metaclass=PoolMeta):
    __name__ = 'account.invoice.credit.start'

    from_fce = fields.Boolean('From FCE', readonly=True)
    pyafipws_anulacion = fields.Boolean('FCE MiPyme anulación',
        states={'invisible': ~Bool(Eval('from_fce'))},
        help='If true, the FCE was anulled from the customer.')

    @classmethod
    def view_attributes(cls):
        states = {'invisible': ~Bool(Eval('from_fce'))}
        return [
            ('/form//image[@name="tryton-dialog-warning"]', 'states', states),
            ('/form//label[@id="credit_fce"]', 'states', states),
            ]


class CreditInvoice(metaclass=PoolMeta):
    __name__ = 'account.invoice.credit'

    def default_start(self, fields):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Date = pool.get('ir.date')

        default = super().default_start(fields)
        default.update({
            'from_fce': False,
            'pyafipws_anulacion': False,
            'invoice_date': Date.today(),
            })
        for invoice in Invoice.browse(Transaction().context['active_ids']):
            if (invoice.type == 'out' and invoice.invoice_type.invoice_type in
                    ('201', '206', '211')):
                default['from_fce'] = True
                break
        return default

    def do_credit(self, action):
        pool = Pool()
        Invoice = pool.get('account.invoice')

        credit_options = dict(
            refund=self.start.with_refund,
            invoice_date=self.start.invoice_date,
            pyafipws_anulacion=self.start.pyafipws_anulacion,
            )
        invoices = Invoice.browse(Transaction().context['active_ids'])

        credit_invoices = Invoice.credit(invoices, **credit_options)

        data = {'res_id': [i.id for i in credit_invoices]}
        if len(credit_invoices) == 1:
            action['views'].reverse()
        return action, data


class InvoiceCmpAsoc(ModelSQL):
    'Invoice - CmpAsoc (Invoice)'
    __name__ = 'account.invoice-cmp.asoc'
    _table = 'account_invoice_cmp_asoc'

    invoice = fields.Many2One('account.invoice', 'Invoice',
        ondelete='CASCADE', required=True)
    cmp_asoc = fields.Many2One('account.invoice', 'Cmp Asoc',
        ondelete='RESTRICT', required=True)
