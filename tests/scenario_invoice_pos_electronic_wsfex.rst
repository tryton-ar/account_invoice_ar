================
Invoice Scenario
================

Imports::
    >>> import datetime
    >>> import io
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from operator import attrgetter
    >>> from proteus import Model, Wizard
    >>> from trytond.tests.tools import activate_modules
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company
    >>> from trytond.modules.currency.tests.tools import get_currency
    >>> from trytond.modules.account.tests.tools import create_fiscalyear, \
    ...     create_chart, get_accounts, create_tax, create_tax_code
    >>> from trytond.modules.account_invoice.tests.tools import \
    ...     set_fiscalyear_invoice_sequences
    >>> from trytond.modules.account_invoice_ar.tests.tools import \
    ...     create_pos, get_invoice_types, get_pos, get_tax_group, get_wsfexv1
    >>> from trytond.modules.party_ar.tests.tools import set_afip_certs
    >>> import pytz
    >>> timezone = pytz.timezone('America/Argentina/Buenos_Aires')
    >>> today = datetime.datetime.now(timezone).date()
    >>> year = int(today.strftime("%Y"))
    >>> month = int(today.strftime("%m"))

Install account_invoice::

    >>> config = activate_modules('account_invoice_ar')

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
    >>> period_ids = [p.id for p in fiscalyear.periods]

Create chart of accounts::

    >>> _ = create_chart(company)
    >>> accounts = get_accounts(company)
    >>> receivable = accounts['receivable']
    >>> revenue = accounts['revenue']
    >>> expense = accounts['expense']
    >>> account_tax = accounts['tax']
    >>> account_cash = accounts['cash']

Create point of sale::

    >>> _ = create_pos(company, type='electronic', number=5000, ws='wsfex')
    >>> pos = get_pos(type='electronic', number=5000)
    >>> pos.number
    5000
    >>> invoice_types = get_invoice_types(pos=pos)

Get tax group IVA Ventas Exento::

    >>> tax_group_exento = get_tax_group('IVA', 'sale', 'exento')

Create tax IVA Exento::

    >>> TaxCode = Model.get('account.tax.code')
    >>> tax = create_tax(Decimal('0'))
    >>> tax.iva_code = '2'
    >>> tax.group = tax_group_exento
    >>> tax.save()
    >>> invoice_base_code = create_tax_code(tax, 'base', 'invoice')
    >>> invoice_base_code.save()
    >>> invoice_tax_code = create_tax_code(tax, 'tax', 'invoice')
    >>> invoice_tax_code.save()
    >>> credit_note_base_code = create_tax_code(tax, 'base', 'credit')
    >>> credit_note_base_code.save()
    >>> credit_note_tax_code = create_tax_code(tax, 'tax', 'credit')
    >>> credit_note_tax_code.save()

Create payment method::

    >>> Journal = Model.get('account.journal')
    >>> PaymentMethod = Model.get('account.invoice.payment.method')
    >>> Sequence = Model.get('ir.sequence')
    >>> journal_cash, = Journal.find([('type', '=', 'cash')])
    >>> payment_method = PaymentMethod()
    >>> payment_method.name = 'Cash'
    >>> payment_method.journal = journal_cash
    >>> payment_method.credit_account = account_cash
    >>> payment_method.debit_account = account_cash
    >>> payment_method.save()

Create Write Off method::

    >>> WriteOff = Model.get('account.move.reconcile.write_off')
    >>> sequence_journal, = Sequence.find(
    ...     [('sequence_type.name', '=', "Account Journal")], limit=1)
    >>> journal_writeoff = Journal(name='Write-Off', type='write-off',
    ...     sequence=sequence_journal)
    >>> journal_writeoff.save()
    >>> writeoff_method = WriteOff()
    >>> writeoff_method.name = 'Rate loss'
    >>> writeoff_method.journal = journal_writeoff
    >>> writeoff_method.credit_account = expense
    >>> writeoff_method.debit_account = expense
    >>> writeoff_method.save()

Create AFIP VAT Country::

    >>> AFIPCountry = Model.get('afip.country')
    >>> sudafrica = AFIPCountry(name='SUDAFRICA', code='159')
    >>> sudafrica.save()

    >>> AFIPVatCountry = Model.get('party.afip.vat.country')
    >>> afip_vat_country = AFIPVatCountry()
    >>> afip_vat_country.vat_number = '55000001715'
    >>> afip_vat_country.afip_country = sudafrica
    >>> afip_vat_country.type_code = '0'
    >>> afip_vat_country.save()

Create party::

    >>> Party = Model.get('party.party')
    >>> party = Party(name='Party')
    >>> tax_identifier = party.identifiers.new()
    >>> tax_identifier.type = 'ar_foreign'
    >>> tax_identifier.code = '55000001715' # SUDAFRICA, Persona Jurídica
    >>> tax_identifier.afip_country = sudafrica
    >>> party.iva_condition = 'cliente_exterior'
    >>> party.save()

Create account category::

    >>> ProductCategory = Model.get('product.category')
    >>> account_category = ProductCategory(name="Account Category")
    >>> account_category.accounting = True
    >>> account_category.account_expense = expense
    >>> account_category.account_revenue = revenue
    >>> account_category.customer_taxes.append(tax)
    >>> account_category.save()

Create product::

    >>> ProductUom = Model.get('product.uom')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> ProductTemplate = Model.get('product.template')
    >>> template = ProductTemplate()
    >>> template.name = 'product'
    >>> template.default_uom = unit
    >>> template.type = 'service'
    >>> template.list_price = Decimal('40')
    >>> template.account_category = account_category
    >>> template.save()
    >>> product, = template.products

Create payment term::

    >>> PaymentTerm = Model.get('account.invoice.payment_term')
    >>> payment_term = PaymentTerm(name='Term')
    >>> line = payment_term.lines.new(type='percent', ratio=Decimal('.5'))
    >>> delta, = line.relativedeltas
    >>> delta.days = 20
    >>> line = payment_term.lines.new(type='remainder')
    >>> delta = line.relativedeltas.new(days=40)
    >>> payment_term.save()

SetUp webservice AFIP::

    >>> wsfexv1 = get_wsfexv1(company, config)

GetLastCMP and configure sequences::

    >>> # cbte_nro = int(wsfexv1.GetLastCMP('19', pos.number))
    >>> cbte_nro = wsfexv1.GetLastCMP('19', pos.number)

    >>> invoice_types['19'].invoice_sequence.number_next = cbte_nro + 1
    >>> invoice_types['19'].invoice_sequence.save()

    >>> cbte_nro = int(wsfexv1.GetLastCMP('20', pos.number))
    >>> invoice_types['20'].invoice_sequence.number_next = cbte_nro + 1
    >>> invoice_types['20'].invoice_sequence.save()

    >>> cbte_nro = int(wsfexv1.GetLastCMP('21', pos.number))
    >>> invoice_types['21'].invoice_sequence.number_next = cbte_nro + 1
    >>> invoice_types['21'].invoice_sequence.save()

Get USD currency and configure rate::

    >>> rate = currency.rates.new()
    >>> rate.date = today
    >>> rate.rate = Decimal(wsfexv1.GetParamCtz('DOL'))
    >>> # rate.get_afip_rate()
    >>> currency.save()

Get USD currency::

    >>> usd = get_currency('USD')
    >>> usd.afip_code = 'DOL'
    >>> usd.save()

Create invoice::

    >>> Invoice = Model.get('account.invoice')
    >>> InvoiceLine = Model.get('account.invoice.line')
    >>> invoice = Invoice()
    >>> invoice.party = party
    >>> invoice.pos = pos
    >>> invoice.payment_term = payment_term
    >>> invoice.currency = currency
    >>> line = InvoiceLine()
    >>> invoice.lines.append(line)
    >>> line.product = product
    >>> line.quantity = 5
    >>> line.unit_price = Decimal('40')
    >>> invoice.untaxed_amount
    Decimal('200.00')
    >>> invoice.tax_amount
    Decimal('0.00')
    >>> invoice.total_amount
    Decimal('200.00')
    >>> invoice.invoice_type == invoice_types['19']
    True
    >>> invoice.save()
    >>> bool(invoice.has_report_cache)
    False

Test change tax::

    >>> tax_line = invoice.taxes[0]
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
    'draft'

Post invoice::

    >>> invoice.pyafipws_concept = '2' # service
    >>> invoice.pyafipws_billing_start_date = datetime.date(year, month, 1)
    >>> invoice.pyafipws_billing_end_date = datetime.date(year, month, 10)
    >>> invoice.pyafipws_incoterms = 'FOB'
    >>> invoice.click('post')
    >>> invoice.state
    'posted'
    >>> # invoice.pyafipws_cae
    >>> # invoice.transactions[0].pyafipws_xml_request
    >>> # invoice.transactions[0].pyafipws_xml_response
    >>> invoice.tax_identifier.code
    '30710158254'
    >>> invoice.untaxed_amount
    Decimal('200.00')
    >>> invoice.tax_amount
    Decimal('0.00')
    >>> invoice.total_amount
    Decimal('200.00')
    >>> receivable.reload()
    >>> receivable.debit
    Decimal('200.00')
    >>> receivable.credit
    Decimal('0.00')
    >>> revenue.reload()
    >>> revenue.debit
    Decimal('0.00')
    >>> revenue.credit
    Decimal('200.00')
    >>> account_tax.reload()
    >>> account_tax.debit
    Decimal('0.00')
    >>> account_tax.credit
    Decimal('0.00')
    >>> with config.set_context(periods=period_ids):
    ...     invoice_base_code = TaxCode(invoice_base_code.id)
    ...     invoice_base_code.amount
    Decimal('200.00')
    >>> with config.set_context(periods=period_ids):
    ...     invoice_tax_code = TaxCode(invoice_tax_code.id)
    ...     invoice_tax_code.amount
    Decimal('0.00')
    >>> with config.set_context(periods=period_ids):
    ...     credit_note_base_code = TaxCode(credit_note_base_code.id)
    ...     credit_note_base_code.amount
    Decimal('0.00')
    >>> with config.set_context(periods=period_ids):
    ...     credit_note_tax_code = TaxCode(credit_note_tax_code.id)
    ...     credit_note_tax_code.amount
    Decimal('0.00')

Credit invoice with refund::

    >>> credit = Wizard('account.invoice.credit', [invoice])
    >>> credit.form.with_refund = True
    >>> credit.form.invoice_date = invoice.invoice_date
    >>> credit.execute('credit')
    >>> credit_note, = Invoice.find([
    ...     ('type', '=', 'out'), ('id', '!=', invoice.id)])
    >>> credit_note.state
    'paid'
    >>> # credit_note.pyafipws_cae
    >>> # credit_note.transactions[0].pyafipws_xml_request
    >>> # credit_note.transactions[0].pyafipws_xml_response
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
    >>> credit_note.invoice_type == invoice_types['21']
    True
    >>> credit_note.reference == invoice.number
    True
    >>> invoice.reload()
    >>> invoice.state
    'cancelled'
    >>> invoice.reconciled == today
    True
    >>> receivable.reload()
    >>> receivable.debit
    Decimal('200.00')
    >>> receivable.credit
    Decimal('200.00')
    >>> revenue.reload()
    >>> revenue.debit
    Decimal('200.00')
    >>> revenue.credit
    Decimal('200.00')
    >>> account_tax.reload()
    >>> account_tax.debit
    Decimal('0.00')
    >>> account_tax.credit
    Decimal('0.00')

Test post without point of sale::

    >>> invoice, = invoice.duplicate()
    >>> invoice.currency = currency
    >>> invoice.pyafipws_concept
    '2'
    >>> invoice.pyafipws_incoterms
    'FOB'
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
    'draft'

Test post when clear tax_identifier type::

    >>> tax_identifier, = company.party.identifiers
    >>> tax_identifier.type = None
    >>> tax_identifier.save()

    >>> invoice.click('post')  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    UserError: ...
    >>> invoice.state
    'draft'

    >>> tax_identifier, = company.party.identifiers
    >>> tax_identifier.type = 'ar_cuit'
    >>> tax_identifier.save()

Pay invoice::

    >>> invoice.pos = pos
    >>> invoice.pyafipws_incoterms = 'FOB'
    >>> invoice.click('post')
    >>> pay = Wizard('account.invoice.pay', [invoice])
    >>> pay.form.amount
    Decimal('200.00')
    >>> pay.form.amount = Decimal('110.00')
    >>> pay.form.payment_method = payment_method
    >>> pay.execute('choice')
    >>> pay.state
    'end'

    >>> pay = Wizard('account.invoice.pay', [invoice])
    >>> pay.form.amount
    Decimal('110.00')
    >>> pay.form.amount = Decimal('10.00')
    >>> pay.form.payment_method = payment_method
    >>> pay.execute('choice')
    >>> pay.form.type = 'partial'
    >>> pay.form.amount
    Decimal('10.00')
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
    Decimal('-10.00')
    >>> pay.form.amount = Decimal('99.00')
    >>> pay.form.payment_method = payment_method
    >>> pay.execute('choice')
    >>> pay.form.type = 'writeoff'
    >>> pay.form.writeoff = writeoff_method
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
    'paid'
    >>> sorted(l.credit for l in invoice.reconciliation_lines)
    [Decimal('1.00'), Decimal('31.00'), Decimal('99.00'), Decimal('131.00')]

Create empty invoice::

    >>> invoice = Invoice()
    >>> invoice.party = party
    >>> invoice.pos = pos
    >>> invoice.pyafipws_concept = '1'
    >>> invoice.pyafipws_incoterms = 'FOB'
    >>> invoice.payment_term = payment_term
    >>> invoice.click('post')  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    UserError: ...
    >>> invoice.state
    'draft'

Create some complex invoice and test its taxes base rounding::

    >>> invoice = Invoice()
    >>> invoice.party = party
    >>> invoice.pos = pos
    >>> invoice.pyafipws_concept = '1'
    >>> invoice.pyafipws_incoterms = 'FOB'
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
    >>> invoice.pyafipws_incoterms = 'FOB'
    >>> invoice.payment_term = payment_term
    >>> line = invoice.lines.new()
    >>> line.product = product
    >>> line.quantity = 5
    >>> line.unit_price = Decimal('40')
    >>> invoice.click('post')
    >>> pay = Wizard('account.invoice.pay', [invoice])
    >>> pay.form.payment_method = payment_method
    >>> pay.execute('choice')
    >>> pay.state
    'end'
    >>> invoice.tax_identifier.type
    'ar_cuit'
    >>> invoice.state
    'paid'

The invoice is posted when the reconciliation is deleted::

    >>> invoice.payment_lines[0].reconciliation.delete()
    >>> invoice.reload()
    >>> invoice.state
    'posted'
    >>> invoice.tax_identifier.type
    'ar_cuit'

Credit invoice with non line lines::

    >>> invoice = Invoice()
    >>> invoice.party = party
    >>> invoice.pos = pos
    >>> invoice.pyafipws_concept = '1'
    >>> invoice.pyafipws_incoterms = 'FOB'
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
    >>> last_cbte_nro = int(wsfexv1.GetLastCMP('19', pos.number))
    >>> invoice, = invoice.duplicate()
    >>> invoice.pyafipws_concept
    '1'
    >>> invoice.pyafipws_cae = posted_invoice.pyafipws_cae
    >>> invoice.pyafipws_cae_due_date = posted_invoice.pyafipws_cae_due_date
    >>> invoice.pos = posted_invoice.pos
    >>> invoice.invoice_type = posted_invoice.invoice_type
    >>> # invoice.number = posted_invoice.number
    >>> invoice.pyafipws_incoterms = posted_invoice.pyafipws_incoterms
    >>> invoice.transactions
    []
    >>> invoice.save()
    >>> invoice.reload()
    >>> invoice.state
    'draft'
    >>> invoice.invoice_date = posted_invoice.invoice_date
    >>> invoice.click('post')
    >>> invoice.state
    'posted'
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
