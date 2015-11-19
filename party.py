#! -*- coding: utf8 -*-
import stdnum.ar.cuit as cuit
import stdnum.exceptions

from trytond.model import ModelView, ModelSQL, fields
from trytond.wizard import Wizard, StateView, StateTransition, Button
from trytond.pyson import Bool, Eval, Equal, Not, And
from trytond.pool   import Pool, PoolMeta
from trytond.transaction import Transaction
from urllib2 import urlopen
from json import loads, dumps

from actividades import CODES

__all__ = ['Party', 'PartyIdentifier', 'AFIPVatCountry', 'GetAFIPData',
    'GetAFIPDataStart']
__metaclass__ = PoolMeta


TIPO_DOCUMENTO = [
('0',  u'CI Policía Federal'),
('1',  u'CI Buenos Aires'),
('2',  u'CI Catamarca'),
('3',  u'CI Córdoba'),
('4',  u'CI Corrientes'),
('5',  u'CI Entre Ríos'),
('6',  u'CI Jujuy'),
('7',  u'CI Mendoza'),
('8',  u'CI La Rioja'),
('9',  u'CI Salta'),
('10', u'CI San Juan'),
('11', u'CI San Luis'),
('12', u'CI Santa Fe'),
('13', u'CI Santiago del Estero'),
('14', u'CI Tucumán'),
('16', u'CI Chaco'),
('17', u'CI Chubut'),
('18', u'CI Formosa'),
('19', u'CI Misiones'),
('20', u'CI Neuquén'),
('21', u'CI La Pampa'),
('22', u'CI Río Negro'),
('23', u'CI Santa Cruz'),
('24', u'CI Tierra del Fuego'),
('80', u'CUIT'),
('86', u'CUIL'),
('87', u'CDI'),
('89', u'LE'),
('90', u'LC'),
('91', u'CI extranjera'),
('92', u'en trámite'),
('93', u'Acta nacimiento'),
('94', u'Pasaporte'),
('95', u'CI Bs. As. RNP'),
('96', u'DNI'),
('99', u'Sin identificar/venta global diaria'),
('30', u'Certificado de Migración'),
('88', u'Usado por Anses para Padrón'),
]
VAT_COUNTRIES = [('', '')]


class Party:
    __name__ = 'party.party'

    iva_condition = fields.Selection(
            [
                ('', ''),
                ('responsable_inscripto', 'Responsable Inscripto'),
                ('exento', 'Exento'),
                ('consumidor_final', 'Consumidor Final'),
                ('monotributo', 'Monotributo'),
                ('no_alcanzado', 'No alcanzado'),
            ],
            'Condicion ante el IVA',
            states={
                'readonly': ~Eval('active', True),
                #'required': Equal(Eval('vat_country'), 'AR'),
                },
            depends=['active'],
            )
    company_name = fields.Char('Company Name',
            states={
                'readonly': ~Eval('active', True),
                },
            depends=['active'],
            )
    company_type = fields.Selection(
            [
                ('', ''),
                ('cooperativa', 'Cooperativa'),
                ('srl', 'SRL'),
                ('sa', 'SA'),
                ('s_de_h', 'S de H'),
                ('estado', 'Estado'),
                ('exterior', 'Exterior'),
            ],
            'Company Type',
            states={
                'readonly': ~Eval('active', True),
                },
            depends=['active'],
            )
    iibb_type = fields.Selection(
            [
                ('', ''),
                ('cm', 'Convenio Multilateral'),
                ('rs', 'Regimen Simplificado'),
                ('exento', 'Exento'),
            ],
            'Inscripcion II BB',
            states={
                'readonly': ~Eval('active', True),
                },
            depends=['active'],
            )
    iibb_number = fields.Char('Nro .II BB',
            states={
                'readonly': ~Eval('active', True),
                'required': And(Not(Equal(Eval('iibb_type'), 'exento')), Bool(Eval('iibb_type')))
                },
            depends=['active'],
            )
    primary_activity_code = fields.Selection(CODES,
            'Primary Activity Code',
            states={
                'readonly': ~Eval('active', True),
                },
            depends=['active'],
            )
    secondary_activity_code = fields.Selection(CODES,
            'Secondary Activity Code',
            states={
                'readonly': ~Eval('active', True),
                },
            depends=['active'],
            )
    start_activity_date = fields.Date('Start activity date',
            states={
                'readonly': ~Eval('active', True),
                },
            depends=['active'],
            )
    controlling_entity = fields.Char('Entidad controladora', help="Controlling entity",
        states={
            'readonly': ~Eval('active', True),
            },
        depends=['active'])
    controlling_entity_number = fields.Char('Nro. entidad controladora', help="Controlling entity",
        states={
            'readonly': ~Eval('active', True),
            },
        depends=['active'])

    tipo_documento = fields.Selection(
            TIPO_DOCUMENTO,
            'Tipo documento',
            states={
                'readonly': ~Eval('active', True),
                },
            depends=['active'],
            )
    vat_number = fields.Function(fields.Char('CUIT'), 'get_vat_number',
            searcher='search_vat_number')
    vat_number_afip_foreign = fields.Function(fields.Char('CUIT AFIP Foreign'),
            'get_vat_number_afip_foreign', searcher='search_vat_number_afip_foreign')


    @staticmethod
    def default_tipo_documento():
        return '80'

    @classmethod
    def __setup__(cls):
        super(Party, cls).__setup__()
        cls._buttons.update({
            'get_afip_data': {},
        })

    def get_vat_number(self, name):
        for identifier in self.identifiers:
            if identifier.type == 'ar_cuit':
                return identifier.code

    @classmethod
    def search_vat_number(cls, name, clause):
        return [
            ('identifiers.code',) + tuple(clause[1:]),
            ('identifiers.type', '=', 'ar_cuit'),
            ]

    def get_vat_number_afip_foreign(self, name):
        for identifier in self.identifiers:
            if identifier.type == 'ar_foreign':
                return identifier.code

    @classmethod
    def search_vat_number_afip_foreign(cls, name, clause):
        return [
            ('identifiers.code',) + tuple(clause[1:]),
            ('identifiers.type', '=', 'ar_foreign'),
            ]

    # Button de AFIP
    @classmethod
    @ModelView.button_action('account_invoice_ar.wizard_get_afip_data')
    def get_afip_data(cls, parties):
        pass


class PartyIdentifier:
    __name__ = 'party.identifier'

    vat_country = fields.Selection(VAT_COUNTRIES, 'VAT Country', states={
        'invisible': ~Equal(Eval('type'), 'ar_foreign'),
        },
        depends=['type'], translate=False)

    @staticmethod
    def default_vat_country():
        return ''

    @classmethod
    def __setup__(cls):
        super(PartyIdentifier, cls).__setup__()
        cls._error_messages.update({
            'unique_vat_number': 'The VAT number must be unique in each Country.',
            'vat_number_not_found': 'El CUIT no ha sido encontrado',
            })
        VAT_COUNTRIES = [('', '')]
        Country = Pool().get('country.country')
        countries = Country.search([('code', '!=', 'AR')])
        for country in countries:
            VAT_COUNTRIES.append((country.code, country.name))
        cls.vat_country.selection = VAT_COUNTRIES

    @classmethod
    def get_types(cls):
        types = super(PartyIdentifier, cls).get_types()
        types.append(('ar_cuit', 'CUIT'))
        types.append(('ar_foreign', 'CUIT AFIP Foreign'))
        return types

    @fields.depends('type', 'code')
    def on_change_with_code(self):
        code = super(PartyIdentifier, self).on_change_with_code()
        if self.type == 'ar_cuit':
            try:
                return cuit.compact(code)
            except stdnum.exceptions.ValidationError:
                pass
        return code

    @classmethod
    def validate(cls, identifiers):
        super(PartyIdentifier, cls).validate(identifiers)
        for identifier in identifiers:
            identifier.check_code()
            if bool(identifier.code) and bool(identifier.vat_country) == False:
                data = cls.search([
                    ('code','=', identifier.code),
                    ])
                if len(data) != 1:
                    cls.raise_user_error('unique_vat_number')

    def check_code(self):
        super(PartyIdentifier, self).check_code()
        if self.type == 'ar_cuit':
            if not cuit.is_valid(self.code):
                self.raise_user_error('invalid_vat', {
                        'code': self.code,
                        'party': self.party.rec_name,
                        })
        elif self.type == 'ar_foreign':
            self.check_foreign_vat()

    def check_foreign_vat(self):
        AFIPVatCountry = Pool().get('party.afip.vat.country')

        if not self.vat_country:
            return

        vat_numbers = AFIPVatCountry.search([
            ('vat_country', '=', self.vat_country),
            ('vat_number', '=', self.code),
            ])

        if not vat_numbers:
            self.raise_user_error('invalid_vat', {
                'code': self.code,
                'party': self.party.rec_name,
                })


class AFIPVatCountry(ModelSQL, ModelView):
    'AFIP Vat Country'
    __name__ = 'party.afip.vat.country'

    vat_number = fields.Char('VAT Number')
    vat_country = fields.Many2One('country.country', 'VAT Country')
    type_code = fields.Selection([
        ('0', 'Juridica'),
        ('1', 'Fisica'),
        ('2', 'Otro Tipo de Entidad'),
        ], 'Type Code')


class GetAFIPDataStart(ModelView):
    'Get AFIP Data Start'
    __name__ = 'party.get_afip_data.start'
    afip_data = fields.Text('Datos extras')
    nombre = fields.Char('Nombre', readonly=True)
    direccion = fields.Char('Direccion', readonly=True)
    codigo_postal = fields.Char('Codigo Postal', readonly=True)
    fecha_inscripcion = fields.Char('Fecha de Inscripcion', readonly=True)
    primary_activity_code = fields.Selection(CODES, 'Actividad primaria', readonly=True)
    secondary_activity_code = fields.Selection(CODES, 'Actividad secundaria', readonly=True)
    estado = fields.Char('Estado', readonly=True)

class GetAFIPData(Wizard):
    'Get AFIP Data'
    __name__ = 'party.get_afip_data'

    start = StateView(
        'party.get_afip_data.start',
        'account_invoice_ar.get_afip_data_start_view', [
            Button('Cancelar', 'end', 'tryton-cancel'),
            Button('OK', 'update_party', 'tryton-ok', default=True),
        ])
    update_party = StateTransition()

    def default_start(self, fields):
        Party = Pool().get('party.party')
        res = {}
        party = Party(Transaction().context['active_id'])
        if party:
            afip_dict = self.get_json(party.vat_number)
            activ  = afip_dict['actividades']
            activ1 = str(activ[0]) if len(activ) >= 1 else ''
            activ2 = str(activ[1]) if len(activ) >= 2 else ''
            if activ1:
                activ1 = activ1.rjust(6, '0')
            if activ2:
                activ2 = activ2.rjust(6, '0')
            res = {
                'nombre': afip_dict['nombre'],
                'direccion': afip_dict['domicilioFiscal']['direccion'],
                'codigo_postal': afip_dict['domicilioFiscal']['codPostal'],
                'fecha_inscripcion': afip_dict['fechaInscripcion'],
                'primary_activity_code': activ1,
                'secondary_activity_code': activ2,
                'estado': afip_dict['estadoClave']
            }

        return res

    def transition_update_party(self):
        # Actualizamos la party con la data que vino de AFIP
        Party = Pool().get('party.party')
        party = Party(Transaction().context.get('active_id'))
        print '   >>> should be updating party...'

        import datetime
        # formato de fecha: AAAA-MM-DD
        fecha = self.start.fecha_inscripcion.split('-')
        if len(fecha) == 3 and len(fecha) == 3:
            year = int(fecha[0])
            month = int(fecha[1])
            day = int(fecha[2])

        party.name = self.start.nombre
        party.primary_activity_code = self.start.primary_activity_code
        party.secondary_activity_code = self.start.secondary_activity_code
        party.vat_country = 'AR'
        party.start_activity_date = datetime.date(year, month, day)
        if self.start.estado == 'ACTIVO':
            party.active = True
        else:
            party.active = False

        # Direccion
        Address = Pool().get('party.address')
        direccion = Address().search(['party', '=', party])

        if len(direccion) > 0 and (direccion[0].street is None or direccion[0].street == ''):
            self._update_direccion(direccion[0], party, self.start)
        else:
            direccion = Address()
            self._update_direccion(direccion, party, self.start)

        party.save()
        return 'end'

    @classmethod
    def _update_direccion(self, direccion, party, start):
        "Actualizamos direccion de una party"
        direccion.name = start.nombre
        direccion.street = start.direccion
        direccion.zip = start.codigo_postal
        direccion.party = party
        direccion.save()

    @classmethod
    def get_json(self, vat_number):
        try:
            afip_url    = 'https://soa.afip.gob.ar/sr-padron/v2/persona/%s' % vat_number
            afip_stream = urlopen(afip_url)
            afip_json   = afip_stream.read()
            afip_dict   = loads(afip_json)
            print "   >>> got json:\n" + dumps(afip_dict)
            return afip_dict['data']
        except Exception:
            self.raise_user_error('vat_number_not_found')
