# This file is part of the account_invoice_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import os
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1
from pyafipws.wsfexv1 import WSFEXv1
from proteus import Model

from trytond.tools import file_open
from trytond.modules.company.tests.tools import get_company
from trytond.modules.party_ar.tests.tools import set_afip_certs

__all__ = ['create_pos', 'get_pos', 'get_invoice_types',
    'create_tax_groups', 'get_wsfev1', 'get_wsfexv1', 'get_filename']


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
    types = ['gravado', 'nacional', 'provincial', 'municipal', 'interno',
        'other']
    groups = {}

    for type in types:
        group = TaxGroup()
        group.name = type
        group.code = type
        group.kind = 'both'
        group.afip_kind = type
        if type == 'nacional':
            group.tribute_id = '1'
        elif type == 'provincial':
            group.tribute_id = '2'
        elif type == 'municipal':
            group.tribute_id = '3'
        elif type == 'interno':
            group.tribute_id = '4'
        elif type == 'other':
            group.tribute_id = '99'
        group.save()
        groups[type] = group
    return groups


def get_wsfev1(company=None, config=None):
    "return wsfev1 object"
    if not company:
        company = get_company()
        company = set_afip_certs(company, config)

    URL_WSAA = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl"
    URL_WSFEv1 = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"
    crt = get_filename('party_ar/tests/gcoop.crt')
    key = get_filename('party_ar/tests/gcoop.key')
    ta = WSAA().Autenticar('wsfe', crt, key, URL_WSAA, cacert=True)
    wsfev1 = WSFEv1()
    wsfev1.LanzarExcepciones = True
    wsfev1.SetTicketAcceso(ta)
    wsfev1.Cuit = company.party.vat_number
    wsfev1.Conectar(wsdl=URL_WSFEv1, cacert=True)
    return wsfev1


def get_wsfexv1(company=None, config=None):
    "return wsfexv1 object"
    if not company:
        company = get_company()
        company = set_afip_certs(company, config)

    URL_WSAA = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl"
    URL_WSFEXv1 = "https://wswhomo.afip.gov.ar/wsfexv1/service.asmx?WSDL"
    crt = get_filename('party_ar/tests/gcoop.crt')
    key = get_filename('party_ar/tests/gcoop.key')
    ta = WSAA().Autenticar('wsfex', crt, key, URL_WSAA, cacert=True)
    wsfexv1 = WSFEXv1()
    wsfexv1.LanzarExcepciones = True
    wsfexv1.SetTicketAcceso(ta)
    wsfexv1.Cuit = company.party.vat_number
    wsfexv1.Conectar(wsdl=URL_WSFEXv1, cacert=True)
    return wsfexv1


def get_filename(name, subdir='modules'):
    """get a filepath from the root dir, using a subdir folder."""
    from trytond.modules import EGG_MODULES
    root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def secure_join(root, *paths):
        "Join paths and ensure it still below root"
        path = os.path.join(root, *paths)
        path = os.path.normpath(path)
        if not path.startswith(os.path.join(root, '')):
            raise IOError("Permission denied: %s" % name)
        return path

    egg_name = False
    if subdir == 'modules':
        module_name = name.split(os.sep)[0]
        if module_name in EGG_MODULES:
            epoint = EGG_MODULES[module_name]
            mod_path = os.path.join(epoint.dist.location,
                    *epoint.module_name.split('.')[:-1])
            mod_path = os.path.abspath(mod_path)
            egg_name = secure_join(mod_path, name)
            if not os.path.isfile(egg_name):
                # Find module in path
                for path in sys.path:
                    mod_path = os.path.join(path,
                            *epoint.module_name.split('.')[:-1])
                    mod_path = os.path.abspath(mod_path)
                    egg_name = secure_join(mod_path, name)
                    if os.path.isfile(egg_name):
                        break
                if not os.path.isfile(egg_name):
                    # When testing modules from setuptools location is the
                    # module directory
                    egg_name = secure_join(
                        os.path.dirname(epoint.dist.location), name)

    if subdir:
        if (subdir == 'modules'
                and (name.startswith('ir' + os.sep)
                    or name.startswith('res' + os.sep)
                    or name.startswith('tests' + os.sep))):
            name = secure_join(root_path, name)
        else:
            name = secure_join(root_path, subdir, name)
    else:
        name = secure_join(root_path, name)

    for i in (name, egg_name):
        if i and os.path.isfile(i):
            return i

    raise IOError('File not found : %s ' % name)
