#!/usr/bin/env python3
# This file is part of the account_invoice_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

import io
import os
import re
from configparser import ConfigParser
from setuptools import find_packages, setup

MODULE = 'account_invoice_ar'
PREFIX = 'trytonar'
MODULE2PREFIX = {
    'account_ar': 'trytonar',
    'bank_ar': 'trytonar',
    'party_ar': 'trytonar',
    }


def read(fname):
    content = io.open(
        os.path.join(os.path.dirname(__file__), fname),
        'r', encoding='utf-8').read()
    content = re.sub(
        r'(?m)^\.\. toctree::\r?\n((^$|^\s.*$)\r?\n)*', '', content)
    return content


def get_require_version(name):
    if name in LINKS:
        return ''  # '%s @ %s' % (name, LINKS[name])
    if minor_version % 2:
        require = '%s >= %s.%s.dev0, < %s.%s'
    else:
        require = '%s >= %s.%s, < %s.%s'
    require %= (name, major_version, minor_version,
        major_version, minor_version + 1)
    return require


config = ConfigParser()
config.read_file(open(os.path.join(os.path.dirname(__file__), 'tryton.cfg')))
info = dict(config.items('tryton'))
for key in ('depends', 'extras_depend', 'xml'):
    if key in info:
        info[key] = info[key].strip().splitlines()
version = info.get('version', '0.0.1')
major_version, minor_version, _ = version.split('.', 2)
major_version = int(major_version)
minor_version = int(minor_version)

url = 'https://github.com/tryton-ar/%s' % MODULE
download_url = 'https://github.com/tryton-ar/%s/tree/%s.%s' % (
    MODULE, major_version, minor_version)

LINKS = {
    'trytonar_account_ar': ('git+https://github.com/tryton-ar/'
        'account_ar.git@%s.%s#egg=trytonar_account_ar-%s.%s' %
        (major_version, minor_version, major_version, minor_version)),
    'trytonar_bank_ar': ('git+https://github.com/tryton-ar/'
        'bank_ar.git@%s.%s#egg=trytonar_bank_ar-%s.%s' %
        (major_version, minor_version, major_version, minor_version)),
    'trytonar_party_ar': ('git+https://github.com/tryton-ar/'
        'party_ar.git@%s.%s#egg=trytonar_party_ar-%s.%s' %
        (major_version, minor_version, major_version, minor_version)),
    }

requires = []
for dep in info.get('depends', []):
    if not re.match(r'(ir|res)(\W|$)', dep):
        module_name = '%s_%s' % (MODULE2PREFIX.get(dep, 'trytond'), dep)
        requires.append(get_require_version(module_name))

requires.append(get_require_version('trytond'))

tests_require = [get_require_version('proteus'), 'pytz']
dependency_links = list(LINKS.values())
if minor_version % 2:
    dependency_links.append('https://trydevpi.tryton.org/')

setup(name='%s_%s' % (PREFIX, MODULE),
    version=version,
    description=('Tryton module to add account invoice (electronic/manual) '
        'localization for Argentina (AFIP)'),
    long_description=read('README.rst'),
    author='tryton-ar',
    url=url,
    download_url=download_url,
    project_urls={
        "Bug Tracker": 'https://github.com/tryton-ar/%s/issues' % MODULE,
        "Documentation": 'https://docs.tryton.org/',
        "Forum": 'https://www.tryton.org/forum',
        "Source Code": url,
        },
    keywords='tryton, invoice, account, argentina, afip',
    package_dir={'trytond.modules.%s' % MODULE: '.'},
    packages=(
        ['trytond.modules.%s' % MODULE]
        + ['trytond.modules.%s.%s' % (MODULE, p) for p in find_packages()]
        ),
    package_data={
        'trytond.modules.%s' % MODULE: (info.get('xml', []) + [
            'tryton.cfg', 'view/*.xml', 'locale/*.po', '*.fodt',
            'tests/*.rst']),
        },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Plugins',
        'Framework :: Tryton',
        'Intended Audience :: Developers',
        'Intended Audience :: Financial and Insurance Industry',
        'Intended Audience :: Legal Industry',
        'License :: OSI Approved :: '
        'GNU General Public License v3 or later (GPLv3+)',
        'Natural Language :: English',
        'Natural Language :: Spanish',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: Implementation :: CPython',
        'Topic :: Office/Business',
        'Topic :: Office/Business :: Financial :: Accounting',
        ],
    license='GPL-3',
    python_requires='>=3.7',
    install_requires=requires,
    extras_require={
        'test': tests_require,
        },
    dependency_links=dependency_links,
    zip_safe=False,
    entry_points="""
    [trytond.modules]
    %s = trytond.modules.%s
    [console_scripts]
    trytond_update_currencies_afip = trytond.modules.%s.scripts.update_currencies:run
    """ % (MODULE, MODULE, MODULE),
    )
