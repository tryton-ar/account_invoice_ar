#!/usr/bin/env python
# -*- coding: utf-8 -*-
# This file is part of the account_invoice_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from setuptools import setup
import re
import os
import ConfigParser


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

config = ConfigParser.ConfigParser()
config.readfp(open('tryton.cfg'))
info = dict(config.items('tryton'))

for key in ('depends', 'extras_depend', 'xml'):
    if key in info:
        info[key] = info[key].strip().splitlines()

major_version, minor_version, _ = info.get('version', '0.0.1').split('.', 2)
major_version = int(major_version)
minor_version = int(minor_version)

#Third party (no tryton modules, required)
requires = []
for dep in info.get('depends', []):
    if dep == 'party_ar':
        requires.append(get_require_version('trytonar_%s' % dep))
    elif dep == 'bank_ar':
        requires.append(get_require_version('trytonar_%s' % dep))
    elif not re.match(r'(ir|res|workflow|webdav)(\W|$)', dep):
        requires.append(get_require_version('trytond_%s' % dep))
requires.append(get_require_version('trytond'))
#requires.append(get_require_version('trytonspain_company_logo'))
requires.append('M2Crypto>=0.22.3')
requires.append('Pillow>=2.8.1')
requires.append('httplib2')
requires.append('pyafipws')
requires.append('pysimplesoap')
#requires.append('suds>=0.4')

tests_require = [get_require_version('proteus'), 'pytz']
dependency_links = [
    'https://github.com/tryton-ar/party_ar/tarball/%s.%s#egg=trytonar_party_ar-%s.%s' \
        % (major_version, minor_version, major_version, minor_version),
    'https://github.com/tryton-ar/bank_ar/tarball/%s.%s#egg=trytonar_bank_ar-%s.%s' \
        % (major_version, minor_version, major_version, minor_version),
    'https://github.com/reingart/pyafipws/tarball/master#egg=pyafipws',
    'https://github.com/pysimplesoap/pysimplesoap/tarball/stable#egg=pysimplesoap',
    ]

setup(name='trytonar_account_invoice_ar',
    version=info.get('version', '0.0.1'),
    description=('Tryton module to add account invoice (electronic/manual) '
        'localizacion for Argentina (AFIP)'),
    author='tryton-ar',
    long_description=read('README.md'),
    url='https://github.com/tryton-ar/account_invoice_ar',
    package_dir={'trytond.modules.account_invoice_ar': '.'},
    packages=[
        'trytond.modules.account_invoice_ar',
    ],
    package_data={
        'trytond.modules.account_invoice_ar': (info.get('xml', [])
                + ['tryton.cfg', 'view/*xml', 'locale/*.po', '*.odt',
                    'icons/*.svg']),
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Plugins',
        'Framework :: Tryton',
        'Intended Audience :: Developers',
        'Intended Audience :: Financial and Insurance Industry',
        'Intended Audience :: Legal Industry',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Natural Language :: English',
        'Natural Language :: Spanish',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.7',
        'Topic :: Office/Business',
        'Topic :: Office/Business :: Financial :: Accounting',
    ],
    license='GPL-3',
    install_requires=requires,
    zip_safe=False,
    entry_points="""
    [trytond.modules]
    account_invoice_ar = trytond.modules.account_invoice_ar
    """,
)
