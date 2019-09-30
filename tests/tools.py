# -*- coding: utf-8 -*-
# This file is part of the account_invoice_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from proteus import Model

from trytond.tools import file_open
from trytond.modules.company.tests.tools import get_company

__all__ = ['create_pos', 'get_pos', 'get_invoice_types',
    'create_tax_groups', 'set_afip_certs']


def create_pos(company=None, type='manual', number=1, ws=None, config=None):
    "Create a Point of Sale"
    Pos = Model.get('account.pos', config=config)
    Sequence = Model.get('ir.sequence', config=config)

    if not company:
        company = get_company()

    pos = Pos(
        company=company.id,
        number=number,
        pos_type=type,
        pyafipws_electronic_invoice_service=ws,
        )

    for attr, name in (
            ('1', u'01-Factura A'),
            ('2', u'02-Nota de Debito A'),
            ('3', u'03-Nota de Credito A'),
            ('4', u'04-Recibos A'),
            ('5', u'05-Nota de Venta al Contado A'),
            ('6', u'06-Factura B'),
            ('7', u'07-Nota de Debito B'),
            ('8', u'08-Nota de Credito B'),
            ('9', u'09-Recibos B'),
            ('10', u'10-Notas de Venta al Contado B'),
            ('11', u'11-Factura C'),
            ('12', u'12-Nota de Debito C'),
            ('13', u'13-Nota de Credito C'),
            ('15', u'15-Recibo C'),
            ('19', u'19-Factura E'),
            ('20', u'20-Nota de Débito E'),
            ('21', u'21-Nota de Crédito E'),
            ('201', u'201-Factura de Crédito Electrónica MiPyMEs (FCE) A'),
            ('202', u'202-Nota de Débito Electrónica MiPyMEs (FCE) A'),
            ('203', u'203-Nota de Crédito Electrónica MiPyMEs (FCE) A'),
            ('206', u'206-Factura de Crédito Electrónica MiPyMEs (FCE) B'),
            ('207', u'207-Nota de Débito Electrónica MiPyMEs (FCE) B'),
            ('208', u'208-Nota de Crédito Electrónica MiPyMEs (FCE) B'),
            ('211', u'211-Factura de Crédito Electrónica MiPyMEs (FCE) C'),
            ('212', u'212-Nota de Débito Electrónica MiPyMEs (FCE) C'),
            ('213', u'213-Nota de Crédito Electrónica MiPyMEs (FCE) C')):
        sequence = Sequence(
            name='%s %s' % (name, type),
            code='account.invoice',
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
    Account = Model.get('account.account', config=config)
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


def create_tax_groups(company=None, config=None):
    "Create tax groups"
    TaxGroup = Model.get('account.tax.group', config=config)
    types = ['iva', 'nacional', 'iibb', 'municipal', 'interno']
    groups = {}

    for type in types:
        group = TaxGroup()
        group.name = type
        group.code = type
        group.kind = 'both'
        group.save()
        groups[type] = group
    return groups


def set_afip_certs(company=None, config=None):
    "Set AFIP certificates"
    if not company:
        company = get_company()
    with file_open('account_invoice_ar/tests/gcoop.crt', mode='rb') as fp:
        crt = fp.read()
        company.pyafipws_certificate = crt.decode('utf8')
    with file_open('account_invoice_ar/tests/gcoop.key', mode='rb') as fp:
        key = fp.read()
        company.pyafipws_private_key = key.decode('utf8')
    company.pyafipws_mode_cert = 'homologacion'
    company.save()
    return company
