#! -*- coding: utf8 -*-
from trytond.model import ModelView, ModelSQL, fields
from trytond.pyson import Bool, Eval, Equal, Not, And

from afip_codigo_actividad import CODES

__all__ = ['Party']

class Party(ModelSQL, ModelView):
    """Pary module, extended for account_invoice_ar"""

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
                'required': Equal(Eval('vat_country'), 'AR'),
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
            'Tipo de Inscripcion de II BB',
            states={
                'readonly': ~Eval('active', True),
                },
            depends=['active'],
            )
    iibb_number = fields.Char('II BB',
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
    vat_number = fields.Char('VAT Number', help="Value Added Tax number",
        states={
            'readonly': ~Eval('active', True),
            'required': And(Bool(Eval('vat_country')), Not(Equal(Eval('iva_condition'), 'consumidor_final'))),
            },
        depends=['active', 'vat_country', 'iva_condition'])
    controlling_entity = fields.Char('Controlling entity', help="Controlling entity",
        states={
            'readonly': ~Eval('active', True),
            },
        depends=['active'])
    controlling_entity_number = fields.Char('Controlling entity number', help="Controlling entity",
        states={
            'readonly': ~Eval('active', True),
            },
        depends=['active'])

    @staticmethod
    def default_vat_country():
        return 'AR'

    @classmethod
    def __setup__(cls):
        super(Party, cls).__setup__()
        cls._error_messages.update({
            'unique_vat_number': 'The VAT number must be unique in each country.',
            })

    @classmethod
    def create(cls, vlist):
        for vals in vlist:
            if 'vat_number' in vals and 'vat_country' in vals:
                data = cls.search([('vat_number','=', vals['vat_number']),
                                   ('vat_country','=', vals['vat_country']),
                                  ])
                if data:
                    cls.raise_user_error('unique_vat_number')

        return super(Party, cls).create(vlist)

    @classmethod
    def write(cls, parties, vals):
        if 'vat_number' in vals and 'vat_country' in vals:
            data = cls.search([('vat_number','=', vals['vat_number']),
                               ('vat_country','=', vals['vat_country']),
                              ])
            if data and data != parties:
                cls.raise_user_error('unique_vat_number')

        return super(Party, cls).write(parties, vals)
        pass
