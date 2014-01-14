#! -*- coding: utf8 -*-

import collections
import logging
from decimal import Decimal

from trytond.model import ModelSQL, Workflow, fields, ModelView
from trytond.report import Report
from trytond.pyson import Eval
from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta


__all__ = ['Invoice', 'AfipWSTransaction', 'InvoiceReport']
__metaclass__ = PoolMeta

_STATES = {
    'readonly': Eval('state') != 'draft',
}
_DEPENDS = ['state']

_BILLING_STATES = _STATES.copy()
_BILLING_STATES.update({
        'required': (Eval('pyafipws_concept') == '2')
                    | (Eval('pyafipws_concept') == '3')
    })

_POS_STATES = _STATES.copy()
_POS_STATES.update({
        'required': Eval('type').in_(['out_invoice', 'out_credit_note']),
        'invisible': Eval('type').in_(['in_invoice', 'in_credit_note']),
            })

IVA_AFIP_CODE = collections.defaultdict(lambda: 0)
IVA_AFIP_CODE.update({
    Decimal('0'): 3,
    Decimal('0.105'): 4,
    Decimal('0.21'): 5,
    Decimal('0.27'): 6,
    })

INVOICE_TYPE_AFIP_CODE = {
        ('out_invoice', 'A'): ('1', u'01-Factura A'),
        ('out_invoice', 'B'): ('6', u'06-Factura B'),
        ('out_invoice', 'C'): ('11', u'11-Factura C'),
        ('out_invoice', 'E'): ('19', u'19-Factura E'),
        ('out_credit_note', 'A'): ('3', u'03-Nota de Crédito A'),
        ('out_credit_note', 'B'): ('8', u'08-Nota de Crédito B'),
        ('out_credit_note', 'C'): ('13', u'13-Nota de Crédito C'),
        ('out_credit_note', 'E'): ('21', u'21-Nota de Crédito E'),
        }


class AfipWSTransaction(ModelSQL, ModelView):
    'AFIP WS Transaction'
    __name__ = 'account_invoice_ar.afip_transaction'

    pyafipws_result = fields.Selection([
           ('', 'n/a'),
           ('A', 'Aceptado'),
           ('R', 'Rechazado'),
           ('O', 'Observado'),
       ], 'Resultado', readonly=True,
       help=u"Resultado procesamiento de la Solicitud, devuelto por AFIP")

    pyafipws_message = fields.Text('Mensaje', readonly=True,
       help=u"Mensaje de error u observación, devuelto por AFIP")
    pyafipws_xml_request = fields.Text('Requerimiento XML', readonly=True,
       help=u"Mensaje XML enviado a AFIP (depuración)")
    pyafipws_xml_response = fields.Text('Respuesta XML', readonly=True,
       help=u"Mensaje XML recibido de AFIP (depuración)")

    invoice = fields.Many2One('account.invoice', 'Invoice')


class Invoice:
    'Invoice'
    __name__ = 'account.invoice'

    pos = fields.Many2One('account.pos', 'Point of Sale',
        on_change=['pos', 'party', 'type', 'company'],
        states=_POS_STATES, depends=_DEPENDS)
    invoice_type = fields.Many2One('account.pos.sequence', 'Invoice Type',
        domain=([('pos', '=', Eval('pos'))]),
        states=_POS_STATES, depends=_DEPENDS)

    pyafipws_concept = fields.Selection([
       ('1', u'1-Productos'),
       ('2', u'2-Servicios'),
       ('3', u'3-Productos y Servicios (mercado interno)'),
       ('4', u'4-Otros (exportación)'),
       ('', ''),
       ], 'Concepto',
       select=True,
       states={
           'readonly': Eval('state') != 'draft',
           'required': Eval('pos.pos_type') == 'electronic',
            }, depends=['state']
       )
    pyafipws_billing_start_date = fields.Date('Fecha Desde',
       states=_BILLING_STATES, depends=_DEPENDS,
       help=u"Seleccionar fecha de fin de servicios - Sólo servicios")
    pyafipws_billing_end_date = fields.Date('Fecha Hasta',
       states=_BILLING_STATES, depends=_DEPENDS,
       help=u"Seleccionar fecha de inicio de servicios - Sólo servicios")
    pyafipws_cae = fields.Char('CAE', size=14, readonly=True,
       help=u"Código de Autorización Electrónico, devuelto por AFIP")
    pyafipws_cae_due_date = fields.Date('Vencimiento CAE', readonly=True,
       help=u"Fecha tope para verificar CAE, devuelto por AFIP")
    pyafipws_barcode = fields.Char(u'Codigo de Barras', size=40,
        help=u"Código de barras para usar en la impresión", readonly=True,)
    pyafipws_number = fields.Char(u'Número', size=13, readonly=True,
            help=u"Número de factura informado a la AFIP")

    transactions = fields.One2Many('account_invoice_ar.afip_transaction',
                                   'invoice', u"Transacciones",
                                   readonly=True)

    @classmethod
    def __setup__(cls):
        super(Invoice, cls).__setup__()

        cls._buttons.update({
            'afip_post': {
                'invisible': ~Eval('state').in_(['draft', 'validated']),
                },
            })
        cls._error_messages.update({
            'missing_pyafipws_billing_date':
                u'Debe establecer los valores "Fecha desde" y "Fecha hasta" ' \
                u'en el Diario, correspondientes al servicio que se está facturando',
            'invalid_invoice_number':
                u'El número de la factura (%d), no coincide con el que espera ' \
                u'la AFIP (%d). Modifique la secuencia del diario',
            'not_cae':
                u'No fue posible obtener el CAE. Revise las Transacciones ' \
                u'para mas información',
            'invalid_journal':
                u'Este diario (%s) no tiene establecido los datos necesaios para ' \
                u'facturar electrónicamente',
            'missing_sequence':
                u'No existe una secuencia para facturas del tipo: %s',
            'too_many_sequences':
                u'Existe mas de una secuencia para facturas del tipo: %s',
            'missing_company_iva_condition': ('The iva condition on company '
                    '"%(company)s" is missing.'),
            'missing_party_iva_condition': ('The iva condition on party '
                    '"%(party)s" is missing.'),
            })

    @classmethod
    def validate(cls, invoices):
        super(Invoice, cls).validate(invoices)
        for invoice in invoices:
            invoice.check_invoice_type()

    def check_invoice_type(self):
        if not self.company.party.iva_condition:
            self.raise_user_error('missing_company_iva_condition', {
                    'company': self.company.rec_name,
                    })
        if not self.party.iva_condition:
            self.raise_user_error('missing_party_iva_condition', {
                    'party': self.party.rec_name,
                    })

    def on_change_pos(self):
        PosSequence = Pool().get('account.pos.sequence')

        if not self.pos:
            return {'invoice_type': None}

        res = {}
        client_iva = company_iva = None
        if self.party:
            client_iva = self.party.iva_condition
        if self.company:
            company_iva = self.company.party.iva_condition

        if company_iva == 'responsable_inscripto':
            if client_iva is None:
                return res
            if client_iva == 'responsable_inscripto':
                kind = 'A'
            elif client_iva == 'consumidor_final':
                kind = 'B'
            elif self.party.vat_country is None:
                self.raise_user_error('unknown_country')
            elif self.party.vat_country == u'AR':
                kind = 'B'
            else:
                kind = 'E'
        else:
            kind = 'C'

        invoice_type, invoice_type_desc = INVOICE_TYPE_AFIP_CODE[
            (self.type, kind)
            ]
        sequences = PosSequence.search([
            ('pos', '=', self.pos.id),
            ('invoice_type', '=', invoice_type)
            ])
        if len(sequences) == 0:
            self.raise_user_error('missing_sequence', invoice_type_desc)
        elif len(sequences) > 1:
            self.raise_user_error('too_many_sequences', invoice_type_desc)
        else:
            res['invoice_type'] = sequences[0].id

        return res

    def set_number(self):
        super(Invoice, self).set_number()

        if self.type == 'out_invoice' or self.type == 'out_credit_note':
            vals = {}
            Sequence = Pool().get('ir.sequence')

            number = Sequence.get_id(self.invoice_type.invoice_sequence.id)
            vals['number'] = '%04d-%08d' % (self.pos.number, int(number))
            self.write([self], vals)

    @classmethod
    @ModelView.button
    @Workflow.transition('posted')
    def post(cls, invoices):
        Move = Pool().get('account.move')

        moves = []
        for invoice in invoices:
            if invoice.pos:
                if invoice.pos.pos_type == 'electronic':
                    invoice.do_pyafipws_request_cae()
                    if not invoice.pyafipws_cae:
                        invoice.raise_user_error('not_cae')
            invoice.set_number()
            moves.append(invoice.create_move())
        Move.post(moves)
        cls.write(invoices, {
                'state': 'posted',
                })
        for invoice in invoices:
            if invoice.type in ('out_invoice', 'out_credit_note'):
                invoice.print_invoice()

    def do_pyafipws_request_cae(self):
        logger = logging.getLogger('pyafipws')
        "Request to AFIP the invoices' Authorization Electronic Code (CAE)"
        # if already authorized (electronic invoice with CAE), ignore
        if self.pyafipws_cae:
            logger.info(u'Se trata de obtener CAE de la factura que ya tiene. '\
                        u'Factura: %s, CAE: %s', self.number, self.pyafipws_cae)
            return
        # get the electronic invoice type, point of sale and service:
        pool = Pool()

        Company = pool.get('company.company')
        company_id = Transaction().context.get('company')
        if not company_id:
            logger.info(u'No hay companía')
            return

        company = Company(company_id)

        tipo_cbte = self.invoice_type.invoice_type
        punto_vta = self.pos.number
        service = self.pos.pyafipws_electronic_invoice_service
        # check if it is an electronic invoice sale point:
        ##TODO
        #if not tipo_cbte:
        #    self.raise_user_error('invalid_sequence', pos.invoice_type.invoice_type)

        # authenticate against AFIP:
        auth_data = company.pyafipws_authenticate(service=service)

        # import the AFIP webservice helper for electronic invoice
        if service == 'wsfe':
            from pyafipws.wsfev1 import WSFEv1  # local market
            ws = WSFEv1()
        #elif service == 'wsmtxca':
        #    from pyafipws.wsmtx import WSMTXCA, SoapFault   # local + detail
        #    ws = WSMTXCA()
        elif service == 'wsfex':
            from pyafipws.wsfexv1 import WSFEXv1 # foreign trade
            ws = WSFEXv1()
        else:
            logger.critical(u'WS no soportado: %s', service)
            return

        # connect to the webservice and call to the test method
        ws.Conectar()
        # set AFIP webservice credentials:
        ws.Cuit = company.party.vat_number
        ws.Token = auth_data['token']
        ws.Sign = auth_data['sign']
        #ws.LanzarExcepciones = True

        # get the last 8 digit of the invoice number
        if self.move:
            cbte_nro = int(self.move.number[-8:])
        else:
            Sequence = pool.get('ir.sequence')
            cbte_nro = int(Sequence(
                self.invoice_type.invoice_sequence.id).get_number_next(''))

        # get the last invoice number registered in AFIP
        if service == "wsfe" or service == "wsmtxca":
            cbte_nro_afip = ws.CompUltimoAutorizado(tipo_cbte, punto_vta)
        elif service == 'wsfex':
            cbte_nro_afip = ws.GetLastCMP(tipo_cbte, punto_vta)
        cbte_nro_next = int(cbte_nro_afip or 0) + 1
        # verify that the invoice is the next one to be registered in AFIP
        if cbte_nro != cbte_nro_next:
            self.raise_user_error('invalid_invoice_number', (cbte_nro, cbte_nro_next))

        # invoice number range (from - to) and date:
        cbte_nro = cbt_desde = cbt_hasta = cbte_nro_next

        if self.invoice_date:
            fecha_cbte = self.invoice_date.strftime("%Y-%m-%d")
        else:
            Date = pool.get('ir.date')
            fecha_cbte = Date.today().strftime("%Y-%m-%d")

        if service != 'wsmtxca':
            fecha_cbte = fecha_cbte.replace("-", "")

        # due and billing dates only for concept "services"
        concepto = tipo_expo = int(self.pyafipws_concept or 0)
        if int(concepto) != 1:

            payments = self.payment_term.compute(self.total_amount, self.currency)
            last_payment = max(payments, key=lambda x:x[0])[0]
            fecha_venc_pago = last_payment.strftime("%Y-%m-%d")
            if service != 'wsmtxca':
                    fecha_venc_pago = fecha_venc_pago.replace("-", "")
            if self.pyafipws_billing_start_date:
                fecha_serv_desde = self.pyafipws_billing_start_date.strftime("%Y-%m-%d")
                if service != 'wsmtxca':
                    fecha_serv_desde = fecha_serv_desde.replace("-", "")
            else:
                fecha_serv_desde = None
            if  self.pyafipws_billing_end_date:
                fecha_serv_hasta = self.pyafipws_billing_end_date.strftime("%Y-%m-%d")
                if service != 'wsmtxca':
                    fecha_serv_hasta = fecha_serv_hasta.replace("-", "")
            else:
                fecha_serv_hasta = None
        else:
            fecha_venc_pago = fecha_serv_desde = fecha_serv_hasta = None

        # customer tax number:
        if self.party.vat_number:
            nro_doc = self.party.vat_number
            if len(nro_doc) < 11:
                tipo_doc = 96           # DNI
            else:
                tipo_doc = 80           # CUIT
        else:
            nro_doc = "0"           # only "consumidor final"
            tipo_doc = 99           # consumidor final

        # invoice amount totals:
        imp_total = str("%.2f" % abs(self.total_amount))
        imp_tot_conc = "0.00"
        imp_neto = str("%.2f" % abs(self.untaxed_amount))
        imp_iva = str("%.2f" % abs(self.tax_amount))
        imp_subtotal = imp_neto  # TODO: not allways the case!
        imp_trib = "0.00"
        imp_op_ex = "0.00"
        if self.currency.code == 'ARS':
            moneda_id = "PES"
            moneda_ctz = 1
        else:
            moneda_id = {'USD':'DOL'}[self.currency.code]
            moneda_ctz = str(self.currency.rate)

        # foreign trade data: export permit, country code, etc.:
        #if invoice.pyafipws_incoterms:
        #    incoterms = invoice.pyafipws_incoterms.code
        #    incoterms_ds = invoice.pyafipws_incoterms.name
        #else:
        #    incoterms = incoterms_ds = None
        if int(tipo_cbte) == 19 and tipo_expo == 1:
            permiso_existente =  "N" or "S"     # not used now
        else:
            permiso_existente = ""
        obs_generales = self.comment
        if self.payment_term:
            forma_pago = self.payment_term.name
            obs_comerciales = self.payment_term.name
        else:
            forma_pago = obs_comerciales = None
        idioma_cbte = 1     # invoice language: spanish / español

        # customer data (foreign trade):
        nombre_cliente = self.party.name
        if self.party.vat_number:
            if self.party.vat_country == "AR":
                # use the Argentina AFIP's global CUIT for the country:
                cuit_pais_cliente = self.party.vat_number
                id_impositivo = None
            else:
                # use the VAT number directly
                id_impositivo = self.party.vat_number
                # TODO: the prefix could be used to map the customer country
                cuit_pais_cliente = None
        else:
            cuit_pais_cliente = id_impositivo = None
        if self.invoice_address:
            address = self.invoice_address
            domicilio_cliente = " - ".join([
                                        address.name or '',
                                        address.street or '',
                                        address.streetbis or '',
                                        address.zip or '',
                                        address.city or '',
                                ])
        else:
            domicilio_cliente = ""
        if self.invoice_address.country:
            # map ISO country code to AFIP destination country code:
            pais_dst_cmp = {
                'ar': 200, 'bo': 202, 'br': 203, 'ca': 204, 'co': 205,
                'cu': 207, 'cl': 208, 'ec': 210, 'us': 212, 'mx': 218,
                'py': 221, 'pe': 222, 'uy': 225, 've': 226, 'cn': 310,
                'tw': 313, 'in': 315, 'il': 319, 'jp': 320, 'at': 405,
                'be': 406, 'dk': 409, 'es': 410, 'fr': 412, 'gr': 413,
                'it': 417, 'nl': 423, 'pt': 620, 'uk': 426, 'sz': 430,
                'de': 438, 'ru': 444, 'eu': 497,
                }[self.invoice_address.country.code.lower()]


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
                if tax.group.name == "IVA":
                    iva_id = IVA_AFIP_CODE[tax.rate]
                    base_imp = ("%.2f" % abs(tax_line.base))
                    importe = ("%.2f" % abs(tax_line.amount))
                    # add the vat detail in the helper
                    ws.AgregarIva(iva_id, base_imp, importe)
                else:
                    if 'impuesto' in tax_line.tax.name.lower():
                        tributo_id = 1  # nacional
                    elif 'iibbb' in tax_line.tax.name.lower():
                        tributo_id = 3  # provincial
                    elif 'tasa' in tax_line.tax.name.lower():
                        tributo_id = 4  # municipal
                    else:
                        tributo_id = 99
                    desc = tax_line.name
                    base_imp = ("%.2f" % abs(tax_line.base))
                    importe = ("%.2f" % abs(tax_line.amount))
                    alic = "%.2f" % tax_line.base
                    # add the other tax detail in the helper
                    ws.AgregarTributo(tributo_id, desc, base_imp, alic, importe)

        # analize line items - invoice detail
        if service in ('wsfex', 'wsmtxca'):
            for line in self.lines:
                codigo = line.product.code
                u_mtx = 1                       # TODO: get it from uom?
                cod_mtx = 'xxx' #FIXME: ean13
                ds = line.description
                qty = line.quantity
                umed = 7                        # TODO: line.uos_id...?
                precio = line.unit_price
                importe = line.get_amount('')
                bonif = None  # line.discount
                for tax in line.taxes:
                    if tax.group.name == "IVA":
                        iva_id = IVA_AFIP_CODE[tax.rate]
                        imp_iva = importe * tax.rate
                #if service == 'wsmtxca':
                #    ws.AgregarItem(u_mtx, cod_mtx, codigo, ds, qty, umed,
                #            precio, bonif, iva_id, imp_iva, importe+imp_iva)
                if service == 'wsfex':
                    ws.AgregarItem(codigo, ds, qty, umed, precio, importe,
                            bonif)

        # Request the authorization! (call the AFIP webservice method)
        try:
            if service == 'wsfe':
                ws.CAESolicitar()
            elif service == 'wsmtxca':
                ws.AutorizarComprobante()
            elif service == 'wsfex':
                ws.Authorize(self.id)
        except SoapFault as fault:
            msg = 'Falla SOAP %s: %s' % (fault.faultcode, fault.faultstring)
        except Exception, e:
            if ws.Excepcion:
                # get the exception already parsed by the helper
                msg = ws.Excepcion + ' ' + e
            else:
                # avoid encoding problem when reporting exceptions to the user:
                import traceback
                import sys
                msg = traceback.format_exception_only(sys.exc_type,
                                                      sys.exc_value)[0]
        else:
            msg = u"\n".join([ws.Obs or "", ws.ErrMsg or ""])
        # calculate the barcode:
        if ws.CAE:
            cae_due = ''.join([c for c in str(ws.Vencimiento or '')
                                       if c.isdigit()])
            bars = ''.join([str(ws.Cuit), "%02d" % int(tipo_cbte),
                              "%04d" % int(punto_vta),
                              str(ws.CAE), cae_due])
            bars = bars + self.pyafipws_verification_digit_modulo10(bars)
        else:
            bars = ""

        AFIP_Transaction = pool.get('account_invoice_ar.afip_transaction')
        with Transaction().new_cursor():
            AFIP_Transaction.create([{'invoice': self,
                                'pyafipws_result': ws.Resultado,
                                'pyafipws_message': msg,
                                'pyafipws_xml_request': ws.XmlRequest,
                                'pyafipws_xml_response': ws.XmlResponse,
                                }])
            Transaction().cursor.commit()

        if ws.CAE:
            # store the results
            vals ={'pyafipws_cae': ws.CAE,
                   'pyafipws_cae_due_date': ws.Vencimiento or None,
                   'pyafipws_barcode': bars,
                   'number': '%04d-%08d' % (self.pos.number, cbte_nro)
                       }
            if not '-' in vals['pyafipws_cae_due_date']:
                fe = vals['pyafipws_cae_due_date']
                vals['pyafipws_cae_due_date'] = '-'.join([fe[:4],fe[4:6],fe[6:8]])

            self.write([self], vals)


    def pyafipws_verification_digit_modulo10(self, codigo):
        "Calculate the verification digit 'modulo 10'"
        # http://www.consejo.org.ar/Bib_elect/diciembre04_CT/documentos/rafip1702.htm
        # Step 1: sum all digits in odd positions, left to right
        codigo = codigo.strip()
        if not codigo or not codigo.isdigit():
            return ''
        etapa1 = sum([int(c) for i,c in enumerate(codigo) if not i%2])
        # Step 2: multiply the step 1 sum by 3
        etapa2 = etapa1 * 3
        # Step 3: start from the left, sum all the digits in even positions
        etapa3 = sum([int(c) for i,c in enumerate(codigo) if i%2])
        # Step 4: sum the results of step 2 and 3
        etapa4 = etapa2 + etapa3
        # Step 5: the minimun value that summed to step 4 is a multiple of 10
        digito = 10 - (etapa4 - (int(etapa4 / 10) * 10))
        if digito == 10:
            digito = 0
        return str(digito)



class InvoiceReport(Report):
    __name__ = 'account.invoice'

    @classmethod
    def parse(cls, report, records, data, localcontext):
        pool = Pool()
        User = pool.get('res.user')
        Invoice = pool.get('account.invoice')

        invoice = records[0]

        user = User(Transaction().user)
        localcontext['barcode_img'] = cls._get_pyafipws_barcode_img(Invoice, invoice)
        localcontext['condicion_iva'] = cls._get_condicion_iva(user.company)
        localcontext['iibb_type'] = cls._get_iibb_type(user.company)
        localcontext['vat_number'] = cls._get_vat_number(user.company)
        localcontext['tipo_comprobante'] = cls._get_tipo_comprobante(Invoice, invoice)
        localcontext['nombre_comprobante'] = cls._get_nombre_comprobante(Invoice, invoice)
        localcontext['codigo_comprobante'] = cls._get_codigo_comprobante(Invoice, invoice)
        localcontext['condicion_iva_cliente'] = cls._get_condicion_iva_cliente(Invoice, invoice)
        localcontext['vat_number_cliente'] = cls._get_vat_number_cliente(Invoice, invoice)
        return super(InvoiceReport, cls).parse(report, records, data,
                localcontext=localcontext)

    @classmethod
    def _get_condicion_iva_cliente(cls, Invoice, invoice):
        return dict(invoice.party._fields['iva_condition'].selection)[invoice.party.iva_condition]

    @classmethod
    def _get_vat_number_cliente(cls, Invoice, invoice):
        value = invoice.party.vat_number
        return '%s-%s-%s' % (value[:2], value[2:-1], value[-1])

    @classmethod
    def _get_tipo_comprobante(cls, Invoice, invoice):
        return dict(invoice.invoice_type._fields['invoice_type'].selection)[invoice.invoice_type.invoice_type][-1]

    @classmethod
    def _get_nombre_comprobante(cls, Invoice, invoice):
        return dict(invoice.invoice_type._fields['invoice_type'].selection)[invoice.invoice_type.invoice_type][3:-2]

    @classmethod
    def _get_codigo_comprobante(cls, Invoice, invoice):
        return dict(invoice.invoice_type._fields['invoice_type'].selection)[invoice.invoice_type.invoice_type][:2]

    @classmethod
    def _get_vat_number(cls, company):
        value = company.party.vat_number
        return '%s-%s-%s' % (value[:2], value[2:-1], value[-1])

    @classmethod
    def _get_condicion_iva(cls, company):
        return dict(company.party._fields['iva_condition'].selection)[company.party.iva_condition]

    @classmethod
    def _get_iibb_type(cls, company):
        return company.party.iibb_type.upper()+' '+company.party.iibb_number

    @classmethod
    def _get_pyafipws_barcode_img(cls, Invoice, invoice):
        "Generate the required barcode Interleaved of 7 image using PIL"
        from pyafipws.pyi25 import PyI25
        from cStringIO import StringIO as StringIO
        # create the helper:
        pyi25 = PyI25()
        output = StringIO()
        if not invoice.pyafipws_barcode:
            return
        # call the helper:
        bars = ''.join([c for c in invoice.pyafipws_barcode if c.isdigit()])
        if not bars:
            bars = "00"
        pyi25.GenerarImagen(bars, output, basewidth=3, width=380, height=50, extension="PNG")
        image = buffer(output.getvalue())
        output.close()
        return image
