# This file is part of the account_invoice_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import os
import sys
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1
from pyafipws.wsfexv1 import WSFEXv1
from proteus import Model

from trytond.modules.company.tests.tools import get_company
from trytond.modules.party_ar.tests.tools import set_afip_certs
from trytond.modules.party_ar.afip import PyAfipWsWrapper

__all__ = ['create_pos', 'get_pos', 'get_invoice_types',
    'get_tax_group', 'get_wsfev1', 'get_wsfexv1']


def create_pos(company=None, type='manual', number=1, ws=None, config=None):
    "Create a Point of Sale"
    Pos = Model.get('account.pos', config=config)
    SequenceType = Model.get('ir.sequence.type', config=config)
    Sequence = Model.get('ir.sequence', config=config)

    if not company:
        company = get_company()

    pos = Pos(
        company=company.id,
        number=number,
        pos_type=type,
        pyafipws_electronic_invoice_service=ws,
        )
    sequence_type, = SequenceType.find([
        ('name', '=', 'Invoice'),
        ], limit=1)

    for attr, name in (
            ('1', '01-Factura A'),
            ('2', '02-Nota de Debito A'),
            ('3', '03-Nota de Credito A'),
            ('4', '04-Recibos A'),
            ('5', '05-Nota de Venta al Contado A'),
            ('6', '06-Factura B'),
            ('7', '07-Nota de Debito B'),
            ('8', '08-Nota de Credito B'),
            ('9', '09-Recibos B'),
            ('10', '10-Notas de Venta al Contado B'),
            ('11', '11-Factura C'),
            ('12', '12-Nota de Debito C'),
            ('13', '13-Nota de Credito C'),
            ('15', '15-Recibo C'),
            ('19', '19-Factura E'),
            ('20', '20-Nota de Débito E'),
            ('21', '21-Nota de Crédito E'),
            ('201', '201-Factura de Crédito Electrónica MiPyMEs (FCE) A'),
            ('202', '202-Nota de Débito Electrónica MiPyMEs (FCE) A'),
            ('203', '203-Nota de Crédito Electrónica MiPyMEs (FCE) A'),
            ('206', '206-Factura de Crédito Electrónica MiPyMEs (FCE) B'),
            ('207', '207-Nota de Débito Electrónica MiPyMEs (FCE) B'),
            ('208', '208-Nota de Crédito Electrónica MiPyMEs (FCE) B'),
            ('211', '211-Factura de Crédito Electrónica MiPyMEs (FCE) C'),
            ('212', '212-Nota de Débito Electrónica MiPyMEs (FCE) C'),
            ('213', '213-Nota de Crédito Electrónica MiPyMEs (FCE) C')):
        sequence = Sequence(
            name='%s %s' % (name, type),
            sequence_type=sequence_type,
            company=company)
        sequence.save()
        pos.pos_sequences.new(
            invoice_type=attr,
            invoice_sequence=sequence,
            )
    pos.save()
    return pos


def get_pos(company=None, type='manual', number=1, config=None):
    "Return the only pos"
    Pos = Model.get('account.pos', config=config)

    if not company:
        company = get_company()

    pos, = Pos.find([
            ('company', '=', company.id),
            ('pos_type', '=', type),
            ('number', '=', number),
            ])
    return pos


def get_invoice_types(company=None, pos=None, config=None):
    "Return invoices types per pos and company"
    PosSequence = Model.get('account.pos.sequence', config=config)

    if not company:
        company = get_company()

    if not pos:
        pos = get_pos(company)

    invoice_types = PosSequence.find([
            ('pos', '=', pos.id),
            ])
    invoice_types = {i.invoice_type: i for i in invoice_types}
    return invoice_types


def get_tax_group(code='IVA', kind='sale', afip_kind='gravado', config=None):
    "Create tax groups"
    TaxGroup = Model.get('account.tax.group', config=config)

    group, = TaxGroup.find([
        ('code', '=', code),
        ('kind', '=', kind),
        ('afip_kind', '=', afip_kind),
    ])

    return group


def get_wsfev1(company=None, config=None):
    "return wsfev1 object"
    if not company:
        company = get_company()
        company = set_afip_certs(company, config)

    URL_WSFEv1 = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"
    URL_WSAA = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl"
    cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
    crt = str(company.pyafipws_certificate)
    key = str(company.pyafipws_private_key)

    ta = PyAfipWsWrapper().authenticate('wsfe', crt, key, wsdl=URL_WSAA, cache=cache)
    wsfev1 = WSFEv1()
    wsfev1.LanzarExcepciones = True
    wsfev1.SetTicketAcceso(ta)
    wsfev1.Cuit = company.party.vat_number
    wsfev1.Conectar(wsdl=URL_WSFEv1, cache=cache, cacert=True)
    return wsfev1


def get_wsfexv1(company=None, config=None):
    "return wsfexv1 object"
    if not company:
        company = get_company()
        company = set_afip_certs(company, config)

    URL_WSAA = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl"
    URL_WSFEXv1 = "https://wswhomo.afip.gov.ar/wsfexv1/service.asmx?WSDL"

    cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
    crt = str(company.pyafipws_certificate)
    key = str(company.pyafipws_private_key)

    ta = PyAfipWsWrapper().authenticate('wsfex', crt, key, wsdl=URL_WSAA, cache=cache)
    wsfexv1 = WSFEXv1()
    wsfexv1.LanzarExcepciones = True
    wsfexv1.SetTicketAcceso(ta)
    wsfexv1.Cuit = company.party.vat_number
    wsfexv1.Conectar(wsdl=URL_WSFEXv1, cache=cache, cacert=True)
    return wsfexv1
