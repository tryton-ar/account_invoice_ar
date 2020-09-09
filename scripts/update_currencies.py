#!/usr/bin/env python3
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
import os
import sys
from argparse import ArgumentParser

try:
    from proteus import Model, config
except ImportError:
    prog = os.path.basename(sys.argv[0])
    sys.exit("proteus must be installed to use %s" % prog)


def update_currencies():
    print("Update currencies", file=sys.stderr)
    Currency = Model.get('currency.currency')

    afip_codes = {
        'ARS': 'PES',
        'USD': 'DOL',
        'EUR': '060',
        'GBP': '021',
        'BRL': '012',
        'UYU': '011',
        }

    records = []
    for code, afip_code in afip_codes.items():
        print(code, file=sys.stderr)
        try:
            currency, = Currency.find([('code', '=', code)])
            currency.afip_code = afip_code
            records.append(currency)
        except Exception:
            pass
    Currency.save(records)


def main(database, config_file=None):
    config.set_trytond(database, config_file=config_file)
    update_currencies()


def run():
    parser = ArgumentParser()
    parser.add_argument('-d', '--database', dest='database')
    parser.add_argument('-c', '--config', dest='config_file',
        help='the trytond config file')

    args = parser.parse_args()
    if not args.database:
        parser.error('Missing database')
    main(args.database, args.config_file)


if __name__ == '__main__':
    run()
