================
Invoice Scenario
================

Imports::
    >>> import datetime
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from operator import attrgetter
    >>> from proteus import config, Model, Wizard
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company
    >>> from trytond.modules.currency.tests.tools import get_currency
    >>> from trytond.modules.account.tests.tools import create_fiscalyear, \
    ...     create_chart, get_accounts, create_tax, set_tax_code
    >>> from trytond.modules.account_invoice.tests.tools import \
    ...     set_fiscalyear_invoice_sequences
    >>> from trytond.modules.account_invoice_ar.tests.tools import \
    ...     create_pos, get_invoice_types, get_pos, create_tax_groups, \
    ...     set_afip_certs
    >>> from trytond.modules.account_invoice_ar.afip_auth import \
    ...     authenticate, get_cache_dir
    >>> from pyafipws.wsfev1 import WSFEv1
    >>> today = datetime.date.today()

Create database::

    >>> config = config.set_trytond()
    >>> config.pool.test = True

Install account_invoice::

    >>> Module = Model.get('ir.module')
    >>> account_invoice_module, = Module.find(
    ...     [('name', '=', 'account_invoice_ar')])
    >>> account_invoice_module.click('install')
    >>> Wizard('ir.module.install_upgrade').execute('upgrade')

Create company::

    >>> currency = get_currency('ARS')
    >>> currency.afip_code = 'PES'
    >>> currency.save()
    >>> _ = create_company(currency=currency)
    >>> company = get_company()
    >>> tax_identifier = company.party.identifiers.new()
    >>> tax_identifier.type = 'ar_cuit'
    >>> tax_identifier.code = '30710158254' # gcoop CUIT
    >>> company.party.iva_condition = 'responsable_inscripto'
    >>> company.party.save()

Configure AFIP certificates::

    >>> _ = set_afip_certs(company=company)

Create fiscal year::

    >>> fiscalyear = set_fiscalyear_invoice_sequences(
    ...     create_fiscalyear(company))
    >>> fiscalyear.click('create_period')
    >>> period = fiscalyear.periods[0]

Create chart of accounts::

    >>> _ = create_chart(company)
    >>> accounts = get_accounts(company)
    >>> receivable = accounts['receivable']
    >>> revenue = accounts['revenue']
    >>> expense = accounts['expense']
    >>> account_tax = accounts['tax']
    >>> account_cash = accounts['cash']

Create point of sale::

    >>> _ = create_pos(company, type='electronic', number=4000, ws='wsfe')
    >>> pos = get_pos(type='electronic', number=4000)
    >>> invoice_types = get_invoice_types(pos=pos)

Create tax groups::

    >>> tax_groups = create_tax_groups()

Create tax IVA 21%::

    >>> tax = set_tax_code(create_tax(Decimal('.21')))
    >>> tax.group = tax_groups['iva']
    >>> tax.save()
    >>> invoice_base_code = tax.invoice_base_code
    >>> invoice_tax_code = tax.invoice_tax_code
    >>> credit_note_base_code = tax.credit_note_base_code
    >>> credit_note_tax_code = tax.credit_note_tax_code

Set Cash journal::

    >>> Journal = Model.get('account.journal')
    >>> journal_cash, = Journal.find([('type', '=', 'cash')])
    >>> journal_cash.credit_account = account_cash
    >>> journal_cash.debit_account = account_cash
    >>> journal_cash.save()

Create Write-Off journal::

    >>> Sequence = Model.get('ir.sequence')
    >>> sequence_journal, = Sequence.find([('code', '=', 'account.journal')])
    >>> journal_writeoff = Journal(name='Write-Off', type='write-off',
    ...     sequence=sequence_journal,
    ...     credit_account=revenue, debit_account=expense)
    >>> journal_writeoff.save()

Create party::

    >>> Party = Model.get('party.party')
    >>> party = Party(name='Party')
    >>> party.iva_condition='responsable_inscripto'
    >>> party.vat_number='30688555872'
    >>> party.save()

Create party consumidor final::

    >>> Party = Model.get('party.party')
    >>> party_cf = Party(name='Party')
    >>> party_cf.iva_condition='consumidor_final'
    >>> party_cf.save()

Create product::

    >>> ProductUom = Model.get('product.uom')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> ProductTemplate = Model.get('product.template')
    >>> Product = Model.get('product.product')
    >>> product = Product()
    >>> template = ProductTemplate()
    >>> template.name = 'product'
    >>> template.default_uom = unit
    >>> template.type = 'service'
    >>> template.list_price = Decimal('40')
    >>> template.cost_price = Decimal('25')
    >>> template.account_expense = expense
    >>> template.account_revenue = revenue
    >>> template.customer_taxes.append(tax)
    >>> template.save()
    >>> product.template = template
    >>> product.save()

Create payment term::

    >>> PaymentTerm = Model.get('account.invoice.payment_term')
    >>> payment_term = PaymentTerm(name='Term')
    >>> line = payment_term.lines.new(type='percent', ratio=Decimal('.5'))
    >>> delta = line.relativedeltas.new(days=20)
    >>> line = payment_term.lines.new(type='remainder')
    >>> delta = line.relativedeltas.new(days=40)
    >>> payment_term.save()

SetUp webservice AFIP::

    >>> URL_WSAA = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl"
    >>> URL_WSFEv1 = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"
    >>> certificate = str(company.pyafipws_certificate)
    >>> private_key = str(company.pyafipws_private_key)
    >>> cache = get_cache_dir()
    >>> auth_data = authenticate('wsfe', certificate, private_key,
    ...     cache=cache, wsdl=URL_WSAA)
    >>> wsfev1 = WSFEv1()
    >>> wsfev1.Cuit = company.party.vat_number
    >>> wsfev1.Token = auth_data['token']
    >>> wsfev1.Sign = auth_data['sign']
    >>> wsfev1.Conectar(wsdl=URL_WSFEv1, cache=cache)
    True

Get CompUltimoAutorizado and configure sequences::

    >>> cbte_nro = int(wsfev1.CompUltimoAutorizado('1', pos.number))
    >>> invoice_types['1'].invoice_sequence.number_next = cbte_nro + 1
    >>> invoice_types['1'].invoice_sequence.save()

    >>> cbte_nro = int(wsfev1.CompUltimoAutorizado('3', pos.number))
    >>> invoice_types['3'].invoice_sequence.number_next = cbte_nro + 1
    >>> invoice_types['3'].invoice_sequence.save()

    >>> cbte_nro = int(wsfev1.CompUltimoAutorizado('6', pos.number))
    >>> invoice_types['6'].invoice_sequence.number_next = cbte_nro + 1
    >>> invoice_types['6'].invoice_sequence.save()

    >>> cbte_nro = int(wsfev1.CompUltimoAutorizado('11', pos.number))
    >>> invoice_types['11'].invoice_sequence.number_next = cbte_nro + 1
    >>> invoice_types['11'].invoice_sequence.save()

Create invoice::

    >>> Invoice = Model.get('account.invoice')
    >>> InvoiceLine = Model.get('account.invoice.line')
    >>> invoice = Invoice()
    >>> invoice.party = party
    >>> invoice.pos = pos
    >>> invoice.payment_term = payment_term
    >>> line = InvoiceLine()
    >>> invoice.lines.append(line)
    >>> line.product = product
    >>> line.quantity = 5
    >>> line.unit_price = Decimal('40')
    >>> line = InvoiceLine()
    >>> invoice.lines.append(line)
    >>> line.account = revenue
    >>> line.description = 'Test'
    >>> line.quantity = 1
    >>> line.unit_price = Decimal(20)
    >>> invoice.untaxed_amount
    Decimal('220.00')
    >>> invoice.tax_amount
    Decimal('42.00')
    >>> invoice.total_amount
    Decimal('262.00')
    >>> invoice.invoice_type == invoice_types['1']
    True
    >>> invoice.save()

Test change tax::

    >>> tax_line, = invoice.taxes
    >>> tax_line.tax == tax
    True
    >>> tax_line.tax = None
    >>> tax_line.tax = tax

Test missing pyafipws_concept at invoice::

    >>> invoice.click('post')  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    UserError: ...
    >>> invoice.state
    u'draft'

Post invoice::

    >>> invoice.pyafipws_concept = '1'
    >>> invoice.click('post')
    >>> invoice.state
    u'posted'
    >>> invoice.company.party.vat_number
    u'30710158254'
    >>> invoice.untaxed_amount
    Decimal('220.00')
    >>> invoice.tax_amount
    Decimal('42.00')
    >>> invoice.total_amount
    Decimal('262.00')
    >>> receivable.reload()
    >>> receivable.debit
    Decimal('262.00')
    >>> receivable.credit
    Decimal('0.00')
    >>> revenue.reload()
    >>> revenue.debit
    Decimal('0.00')
    >>> revenue.credit
    Decimal('220.00')
    >>> account_tax.reload()
    >>> account_tax.debit
    Decimal('0.00')
    >>> account_tax.credit
    Decimal('42.00')
    >>> invoice_base_code.reload()
    >>> invoice_base_code.sum
    Decimal('200.00')
    >>> invoice_tax_code.reload()
    >>> invoice_tax_code.sum
    Decimal('42.00')
    >>> credit_note_base_code.reload()
    >>> credit_note_base_code.sum
    Decimal('0.00')
    >>> credit_note_tax_code.reload()
    >>> credit_note_tax_code.sum
    Decimal('0.00')

Credit invoice with refund::

    >>> credit = Wizard('account.invoice.credit', [invoice])
    >>> credit.form.with_refund = True
    >>> credit.execute('credit')
    >>> credit_note, = Invoice.find([
    ...     ('type', '=', 'out'), ('id', '!=', invoice.id)])
    >>> credit_note.state
    u'paid'
    >>> credit_note.untaxed_amount == -invoice.untaxed_amount
    True
    >>> credit_note.tax_amount == -invoice.tax_amount
    True
    >>> credit_note.total_amount == -invoice.total_amount
    True
    >>> credit_note.origins == invoice.rec_name
    True
    >>> credit_note.pos == pos
    True
    >>> credit_note.invoice_type == invoice_types['3']
    True
    >>> invoice.reload()
    >>> invoice.state
    u'paid'
    >>> invoice.reconciled
    True
    >>> receivable.reload()
    >>> receivable.debit
    Decimal('262.00')
    >>> receivable.credit
    Decimal('262.00')
    >>> revenue.reload()
    >>> revenue.debit
    Decimal('220.00')
    >>> revenue.credit
    Decimal('220.00')
    >>> account_tax.reload()
    >>> account_tax.debit
    Decimal('42.00')
    >>> account_tax.credit
    Decimal('42.00')
    >>> invoice_base_code.reload()
    >>> invoice_base_code.sum
    Decimal('200.00')
    >>> invoice_tax_code.reload()
    >>> invoice_tax_code.sum
    Decimal('42.00')
    >>> credit_note_base_code.reload()
    >>> credit_note_base_code.sum
    Decimal('200.00')
    >>> credit_note_tax_code.reload()
    >>> credit_note_tax_code.sum
    Decimal('42.00')

Test post without point of sale::

    >>> invoice, = invoice.duplicate()
    >>> invoice.pyafipws_concept
    u'1'
    >>> invoice.pyafipws_cae
    >>> invoice.pyafipws_cae_due_date
    >>> invoice.pos
    >>> invoice.invoice_type
    >>> invoice.transactions
    []
    >>> invoice.click('post')  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    UserError: ...
    >>> invoice.state
    u'draft'

Test post when clear tax_identifier type::

    >>> tax_identifier, = company.party.identifiers
    >>> tax_identifier.type = None
    >>> tax_identifier.save()

    >>> invoice.pos = pos
    >>> invoice.click('post')  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    UserError: ...
    >>> invoice.state
    u'draft'

    >>> tax_identifier, = company.party.identifiers
    >>> tax_identifier.type = 'ar_cuit'
    >>> tax_identifier.save()

Pay invoice::

    >>> invoice.pos = pos
    >>> invoice.click('post')
    >>> pay = Wizard('account.invoice.pay', [invoice])
    >>> pay.form.amount
    Decimal('262.00')
    >>> pay.form.amount = Decimal('131.00')
    >>> pay.form.journal = journal_cash
    >>> pay.execute('choice')
    >>> pay.state
    'end'

    >>> pay = Wizard('account.invoice.pay', [invoice])
    >>> pay.form.amount
    Decimal('131.00')
    >>> pay.form.amount = Decimal('31.00')
    >>> pay.form.journal = journal_cash
    >>> pay.execute('choice')
    >>> pay.form.type = 'partial'
    >>> pay.form.amount
    Decimal('31.00')
    >>> len(pay.form.lines_to_pay)
    1
    >>> len(pay.form.payment_lines)
    0
    >>> len(pay.form.lines)
    1
    >>> pay.form.amount_writeoff
    Decimal('100.00')
    >>> pay.execute('pay')

    >>> pay = Wizard('account.invoice.pay', [invoice])
    >>> pay.form.amount
    Decimal('-31.00')
    >>> pay.form.amount = Decimal('99.00')
    >>> pay.form.journal = journal_cash
    >>> pay.execute('choice')
    >>> pay.form.type = 'writeoff'
    >>> pay.form.journal_writeoff = journal_writeoff
    >>> pay.form.amount
    Decimal('99.00')
    >>> len(pay.form.lines_to_pay)
    1
    >>> len(pay.form.payment_lines)
    1
    >>> len(pay.form.lines)
    1
    >>> pay.form.amount_writeoff
    Decimal('1.00')
    >>> pay.execute('pay')

    >>> invoice.state
    u'paid'

Create empty invoice::

    >>> invoice = Invoice()
    >>> invoice.party = party
    >>> invoice.pos = pos
    >>> invoice.pyafipws_concept = '1'
    >>> invoice.payment_term = payment_term
    >>> invoice.click('post')
    >>> invoice.state
    u'paid'

Create some complex invoice and test its taxes base rounding::

    >>> invoice = Invoice()
    >>> invoice.party = party
    >>> invoice.pos = pos
    >>> invoice.pyafipws_concept = '1'
    >>> invoice.payment_term = payment_term
    >>> invoice.invoice_date = today
    >>> line = invoice.lines.new()
    >>> line.product = product
    >>> line.quantity = 1
    >>> line.unit_price = Decimal('0.0035')
    >>> line = invoice.lines.new()
    >>> line.product = product
    >>> line.quantity = 1
    >>> line.unit_price = Decimal('0.0035')
    >>> invoice.save()
    >>> invoice.untaxed_amount
    Decimal('0.00')
    >>> invoice.taxes[0].base == invoice.untaxed_amount
    True
    >>> found_invoice, = Invoice.find([('untaxed_amount', '=', Decimal(0))])
    >>> found_invoice.id == invoice.id
    True
    >>> found_invoice, = Invoice.find([('total_amount', '=', Decimal(0))])
    >>> found_invoice.id == invoice.id
    True

Create a paid invoice::

    >>> invoice = Invoice()
    >>> invoice.party = party
    >>> invoice.pos = pos
    >>> invoice.pyafipws_concept = '1'
    >>> invoice.payment_term = payment_term
    >>> line = invoice.lines.new()
    >>> line.product = product
    >>> line.quantity = 5
    >>> line.unit_price = Decimal('40')
    >>> invoice.click('post')
    >>> pay = Wizard('account.invoice.pay', [invoice])
    >>> pay.form.journal = journal_cash
    >>> pay.execute('choice')
    >>> pay.state
    'end'
    >>> invoice.state
    u'paid'

The invoice is posted when the reconciliation is deleted::

    >>> invoice.payment_lines[0].reconciliation.delete()
    >>> invoice.reload()
    >>> invoice.state
    u'posted'

Credit invoice with non line lines::

    >>> invoice = Invoice()
    >>> invoice.party = party
    >>> invoice.pos = pos
    >>> invoice.pyafipws_concept = '1'
    >>> invoice.payment_term = payment_term
    >>> line = invoice.lines.new()
    >>> line.product = product
    >>> line.quantity = 5
    >>> line.unit_price = Decimal('40')
    >>> line = invoice.lines.new()
    >>> line.type = 'comment'
    >>> line.description = 'Comment'
    >>> invoice.click('post')
    >>> credit = Wizard('account.invoice.credit', [invoice])
    >>> credit.form.with_refund = True
    >>> credit.execute('credit')

Duplicate and test recover last posted invoice::

    >>> posted_invoice = Invoice.find([
    ...     ('type', '=', 'out'), ('state', '=', 'posted')])[0]
    >>> last_cbte_nro = int(wsfev1.CompUltimoAutorizado('1', pos.number))
    >>> invoice, = invoice.duplicate()
    >>> invoice.pyafipws_concept
    u'1'
    >>> invoice.pyafipws_cae = posted_invoice.pyafipws_cae
    >>> invoice.pyafipws_cae_due_date = posted_invoice.pyafipws_cae_due_date
    >>> invoice.pos = posted_invoice.pos
    >>> invoice.invoice_type = posted_invoice.invoice_type
    >>> invoice.number = posted_invoice.number
    >>> invoice.transactions
    []
    >>> invoice.save()
    >>> invoice.reload()
    >>> invoice.state
    u'draft'
    >>> invoice.invoice_date = posted_invoice.invoice_date
    >>> invoice.click('post')
    >>> invoice.state
    u'posted'
    >>> bool(invoice.move)
    True
    >>> invoice.pos == posted_invoice.pos
    True
    >>> invoice.invoice_type == posted_invoice.invoice_type
    True
    >>> # invoice.number == posted_invoice.number
    # True
    >>> # invoice.pyafipws_cae == posted_invoice.pyafipws_cae
    # True
    >>> # invoice.transactions[-1].pyafipws_result == posted_invoice.transactions[-1].pyafipws_result
    # True
    >>> # posted_invoice.transactions[-1].pyafipws_xml_request
    >>> # invoice.transactions[-1].pyafipws_xml_request
    >>> # posted_invoice.transactions[-1].pyafipws_xml_response
    >>> # invoice.transactions[-1].pyafipws_xml_response

Post wrong invoice, number and invoice_date should be None::

    >>> company.party.iva_condition = 'monotributo'
    >>> company.party.save()

    >>> invoice = Invoice()
    >>> invoice.party = party
    >>> invoice.pos = pos
    >>> invoice.pyafipws_concept = '1'
    >>> invoice.payment_term = payment_term
    >>> line = invoice.lines.new()
    >>> line.product = product
    >>> line.quantity = 5
    >>> line.unit_price = Decimal('40')
    >>> invoice.invoice_type = invoice_types['11'] # Factura C
    >>> bool(invoice.move)
    False
    >>> invoice.state
    'draft'
    >>> invoice.number
    >>> invoice.invoice_date
    >>> invoice.click('post')  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    UserError: ...
    >>> invoice.state
    u'draft'
    >>> bool(invoice.move)
    False
    >>> invoice.number
    >>> invoice.invoice_date

    >>> company.party.iva_condition = 'responsable_inscripto'
    >>> company.party.save()
