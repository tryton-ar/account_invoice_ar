#! -*- coding: utf8 -*-

from trytond.model import ModelSQL, Workflow, fields, ModelView
from trytond.pyson import Eval
from trytond.transaction import Transaction
from trytond.pool import Pool

from decimal import Decimal
import collections

__all__ = ['ElectronicInvoice', 'AfipWSTransaction']

_STATES = {
    'readonly': Eval('state') != 'draft',
}

_BILLING_STATES = _STATES.copy()
_BILLING_STATES.update({
        'required': (Eval('pyafipws_concept') == '2')
                    | (Eval('pyafipws_concept') == '3')
    })


IVA_AFIP_CODE = collections.defaultdict(lambda: 0)
IVA_AFIP_CODE.update({
    Decimal('0'): 3,
    Decimal('10.5'): 4,
    Decimal('21'): 5,
    Decimal('27'): 6,
    })

class AfipWSTransaction(ModelView, ModelSQL):
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


class ElectronicInvoice(Workflow, ModelSQL):
    'Electronic Invoice'
    __name__ = 'account.invoice'

    pyafipws_concept = fields.Selection([
                   ('1',u'1-Productos'),
                   ('2',u'2-Servicios'),
                   ('3',u'3-Productos y Servicios (mercado interno)'),
                   ('4',u'4-Otros (exportación)'),
                   ], 'Concepto',
                   select=True, required=True,
                   states=_STATES)
    pyafipws_billing_start_date = fields.Date('Fecha Desde',
       states=_BILLING_STATES,
       help=u"Seleccionar fecha de fin de servicios - Sólo servicios")
    pyafipws_billing_end_date = fields.Date('Fecha Hasta',
       states=_BILLING_STATES,
       help=u"Seleccionar fecha de inicio de servicios - Sólo servicios")
    pyafipws_cae = fields.Char('CAE', size=14, readonly=True,
       help=u"Código de Autorización Electrónico, devuelto por AFIP")
    pyafipws_cae_due_date = fields.Date('Vencimiento CAE', readonly=True,
       help=u"Fecha tope para verificar CAE, devuelto por AFIP")
    pyafipws_barcode = fields.Char(u'Codigo de Barras', size=40,
        help=u"Código de barras para usar en la impresión", readonly=True,)

    transactions = fields.One2Many('account_invoice_ar.afip_transaction',
                                   'invoice', u"Transacciones",
                                   readonly=True)
    @classmethod
    def __setup__(cls):
        super(ElectronicInvoice, cls).__setup__()

        cls._buttons.update({
            'pyafipws_request_cae': {},
            })
        cls._error_messages.update({
            'missing_pyafipws_billing_date':
                u'Debe establecer lose valores "Fecha desde" y "Fecha hasta" ' \
                u'en el Diario, correspondientes al servicio que se está facturando'})

    def do_pyafipws_request_cae(self, *args):
        "Request to AFIP the invoices' Authorization Electronic Code (CAE)"
        # if already authorized (electronic invoice with CAE), ignore
        if self.pyafipws_cae:
            print 'hay cae'
            return
        # get the electronic invoice type, point of sale and service:
        journal = self.journal
        Company = Pool().get('company.company')
        company_id = Transaction().context.get('company')
        if not company_id:
            #FIXME: raise error
            print 'no hay company_id'
            return
        company = Company(company_id)

        tipo_cbte = journal.pyafipws_invoice_type
        punto_vta = journal.pyafipws_point_of_sale
        service = journal.pyafipws_electronic_invoice_service
        # check if it is an electronic invoice sale point:
        if not tipo_cbte or not punto_vta or not service:
            #FIXME: raise error
            # Este diario no opera con CAE,
            print 'no hay tipo_cbte, punto_vta, service'
            return

        # authenticate against AFIP:
        auth_data = company.pyafipws_authenticate(service=service)

        # import the AFIP webservice helper for electronic invoice
        if service == 'wsfe':
            from pyafipws.wsfev1 import WSFEv1, SoapFault   # local market
            ws = WSFEv1()
#        elif service == 'wsmtxca':
#            from pyafipws.wsmtx import WSMTXCA, SoapFault   # local + detail
#            ws = WSMTXCA()
        elif service == 'wsfex':
            from pyafipws.wsfexv1 import WSFEXv1, SoapFault # foreign trade
            ws = WSFEXv1()
        else:
            #FIXME: raise error'Error !', "%s no soportado" % service
            return

        # connect to the webservice and call to the test method
        ws.Conectar()
        # set AFIP webservice credentials:
        ws.Cuit = company.party.vat_number
        ws.Token = auth_data['token']
        ws.Sign = auth_data['sign']

        # get the last 8 digit of the invoice number
        cbte_nro = int(self.number[-8:])
        # get the last invoice number registered in AFIP
        if service == "wsfe" or service == "wsmtxca":
            cbte_nro_afip = ws.CompUltimoAutorizado(tipo_cbte, punto_vta)
        elif service == 'wsfex':
            cbte_nro_afip = ws.GetLastCMP(tipo_cbte, punto_vta)
        cbte_nro_next = int(cbte_nro_afip or 0) + 1
        # verify that the invoice is the next one to be registered in AFIP
        if cbte_nro != cbte_nro_next:
            #FIXME: raise error 'Error !',
            #        'Referencia: %s \n'
            #        'El número del comprobante debería ser %s y no %s' % (
            #        str(invoice.number), str(cbte_nro_next), str(cbte_nro)))
            print "cbte_nro != cbte_nro_next", cbte_nro, cbte_nro_next
            return

        # invoice number range (from - to) and date:
        cbte_nro = cbt_desde = cbt_hasta = cbte_nro_next
        fecha_cbte = self.invoice_date.strftime("%Y-%m-%d")
        if service != 'wsmtxca':
            fecha_cbte = fecha_cbte.replace("-", "")

        # due and billing dates only for concept "services"
        concepto = tipo_expo = int(self.pyafipws_concept or 0)
        if int(concepto) != 1:

            payments = self.payment_term.compute(self.total_amount, self.currency)
            last_payment = max(payments, key=lambda x:x[0])[0]
            fecha_venc_pago = last_payment.strftim("%Y-%m-%d")
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
                    fecha_serv_desde = fecha_serv_desde.replace("-", "")
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
                    iva_id = IVA_AFIP_CODE[tax.percentage]
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
                bonif =  None # line.discount
                for tax in line.taxes:
                    if tax.group.name == "IVA":
                        iva_id = IVA_AFIP_CODE[tax.percentage]
                        imp_iva = (importe * tax.percentage).quantize(Decimal('0.01'))
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
                msg = ws.Excepcion
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

        AFIP_Transaction = Pool().get('account_invoice_ar.afip_transaction')
        AFIP_Transaction.create([{'invoice': self,
                            'pyafipws_result': ws.Resultado,
                            'pyafipws_message': msg,
                            'pyafipws_xml_request': ws.XmlRequest,
                            'pyafipws_xml_response': ws.XmlResponse,
                            }])

        import ipdb; ipdb.set_trace()

        if ws.CAE:
            # store the results
            vals ={'pyafipws_cae': ws.CAE,
                        'pyafipws_cae_due_date': ws.Vencimiento or None,
                        'pyafipws_barcode': bars,
                       }
            self.write([self], vals)

        return msg, ws.Resultado

    @classmethod
    @ModelView.button
    def pyafipws_request_cae(cls, invoices):
        "Request to AFIP the invoices' Authorization Electronic Code (CAE)"
        for i, invoice in enumerate(invoices):
            # request authorization (CAE)
            msg, resultado = invoice.do_pyafipws_request_cae()
            if not invoice.pyafipws_cae and msg:
                # notify the user with an exception message
                #FIXME: raise ('Error al solicitar CAE AFIP', msg)
                return
            else:
                # TODO: use better notification (log not shown in workflow)
                msg = "CAE: %s Vto.: %s Resultado: %s"
                msg = msg % (invoice.pyafipws_cae,
                             invoice.pyafipws_cae_due_date,
                             resultado)
                print msg

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

    def _get_pyafipws_barcode_img(self, cr, uid, ids, field_name, arg, context):
        "Generate the required barcode Interleaved of 7 image using PIL"
        from pyafipws.pyi25 import PyI25
        from cStringIO import StringIO as StringIO
        # create the helper:
        pyi25 = PyI25()
        images = {}
        for invoice in self.browse(cr, uid, ids):
            if not invoice.pyafipws_barcode:
                continue
            output = StringIO()
            # call the helper:
            bars = ''.join([c for c in invoice.pyafipws_barcode if c.isdigit()])
            if not bars:
                bars = "00"
            pyi25.GenerarImagen(bars, output, extension="PNG")
            # get the result and encode it for openerp binary field:
            images[invoice.id] = output.getvalue().encode("base64")
            output.close()
        return images
