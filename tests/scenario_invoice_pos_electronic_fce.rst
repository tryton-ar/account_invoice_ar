================
Invoice Scenario
================

Imports::
    >>> import datetime
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
    ...     create_pos, get_invoice_types, get_pos, create_tax_groups, get_wsfev1
    >>> from trytond.modules.party_ar.tests.tools import set_afip_certs
    >>> import pytz
    >>> timezone = pytz.timezone('America/Argentina/Buenos_Aires')
    >>> today = datetime.datetime.now(timezone).date()

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

Configure company timezone::

    >>> company.timezone = 'America/Argentina/Buenos_Aires'
    >>> company.save()

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

    >>> _ = create_pos(company, type='electronic', number=4000, ws='wsfe')
    >>> pos = get_pos(type='electronic', number=4000)
    >>> invoice_types = get_invoice_types(pos=pos)

Create tax groups::

    >>> tax_groups = create_tax_groups()

Create tax IVA 21%::

    >>> TaxCode = Model.get('account.tax.code')
    >>> tax = create_tax(Decimal('.21'))
    >>> tax.group = tax_groups['gravado']
    >>> tax.iva_code = '5'
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

Create party::

    >>> Party = Model.get('party.party')
    >>> party = Party(name='Party')
    >>> party.iva_condition='responsable_inscripto'
    >>> party.vat_number='30571421352' # CUIT credicoop
    >>> party.pyafipws_fce = True
    >>> party.pyafipws_fce_amount = Decimal('50000')
    >>> party.save()

Create bank party::

    >>> Party = Model.get('party.party')
    >>> party_bank = Party(name='Party')
    >>> party_bank.iva_condition = 'responsable_inscripto'
    >>> party_bank.vat_number='33999242109' # CUIT BAPRO 
    >>> party_bank.save()

Create a bank::

    >>> Bank = Model.get('bank')
    >>> bank = Bank()
    >>> bank.party = party_bank
    >>> bank.save()

Create bank account::

    >>> BankAccount = Model.get('bank.account')
    >>> Number = Model.get('bank.account.number')
    >>> account_bank = BankAccount()
    >>> account_bank.bank = bank
    >>> account_bank.journal = journal_cash
    >>> account_bank.credit_account = account_cash 
    >>> account_bank.debit_account = account_cash
    >>> account_bank.pyafipws_cbu = True
    >>> account_bank.owners.append(company.party)
    >>> number = Number()
    >>> number.type = 'cbu'
    >>> number.number = '2850590940090418135201'
    >>> account_bank.numbers.append(number)
    >>> account_bank.save()
    >>> cbu_number, = account_bank.numbers
    >>> cbu_number.number_compact
    '2850590940090418135201'

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

    >>> wsfev1 = get_wsfev1(company, config)

Get CompUltimoAutorizado and configure sequences::

    >>> cbte_nro = int(wsfev1.CompUltimoAutorizado('1', pos.number))
    >>> invoice_types['1'].invoice_sequence.number_next = cbte_nro + 1
    >>> invoice_types['1'].invoice_sequence.save()

    >>> cbte_nro = int(wsfev1.CompUltimoAutorizado('201', pos.number))
    >>> invoice_types['201'].invoice_sequence.number_next = cbte_nro + 1
    >>> invoice_types['201'].invoice_sequence.save()

    >>> cbte_nro = int(wsfev1.CompUltimoAutorizado('203', pos.number))
    >>> invoice_types['203'].invoice_sequence.number_next = cbte_nro + 1
    >>> invoice_types['203'].invoice_sequence.save()

    >>> cbte_nro = int(wsfev1.CompUltimoAutorizado('206', pos.number))
    >>> invoice_types['206'].invoice_sequence.number_next = cbte_nro + 1
    >>> invoice_types['206'].invoice_sequence.save()

    >>> cbte_nro = int(wsfev1.CompUltimoAutorizado('211', pos.number))
    >>> invoice_types['211'].invoice_sequence.number_next = cbte_nro + 1
    >>> invoice_types['211'].invoice_sequence.save()

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
    >>> line.unit_price = Decimal('20000')
    >>> invoice.untaxed_amount
    Decimal('100000.00')
    >>> invoice.tax_amount
    Decimal('21000.00')
    >>> invoice.total_amount
    Decimal('121000.00')
    >>> invoice.invoice_type == invoice_types['201']
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
    'draft'

Post invoice::

    >>> invoice.pyafipws_concept = '1'
    >>> invoice.pyafipws_cbu == account_bank
    True
    >>> invoice.click('post')
    >>> invoice.state
    'posted'
    >>> invoice.tax_identifier.code
    '30710158254'
    >>> invoice.untaxed_amount
    Decimal('100000.00')
    >>> invoice.tax_amount
    Decimal('21000.00')
    >>> invoice.total_amount
    Decimal('121000.00')
    >>> receivable.reload()
    >>> receivable.debit
    Decimal('121000.00')
    >>> receivable.credit
    Decimal('0.00')
    >>> revenue.reload()
    >>> revenue.debit
    Decimal('0.00')
    >>> revenue.credit
    Decimal('100000.00')
    >>> account_tax.reload()
    >>> account_tax.debit
    Decimal('0.00')
    >>> account_tax.credit
    Decimal('21000.00')
    >>> with config.set_context(periods=period_ids):
    ...     invoice_base_code = TaxCode(invoice_base_code.id)
    ...     invoice_base_code.amount
    Decimal('100000.00')
    >>> with config.set_context(periods=period_ids):
    ...     invoice_tax_code = TaxCode(invoice_tax_code.id)
    ...     invoice_tax_code.amount
    Decimal('21000.00')
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
    >>> credit_note.invoice_type == invoice_types['203']
    True
    >>> invoice.reload()
    >>> invoice.state
    'cancelled'
    >>> invoice.reconciled == today
    True
    >>> receivable.reload()
    >>> receivable.debit
    Decimal('121000.00')
    >>> receivable.credit
    Decimal('121000.00')
    >>> revenue.reload()
    >>> revenue.debit
    Decimal('100000.00')
    >>> revenue.credit
    Decimal('100000.00')
    >>> account_tax.reload()
    >>> account_tax.debit
    Decimal('21000.00')
    >>> account_tax.credit
    Decimal('21000.00')
    >>> with config.set_context(periods=period_ids):
    ...     invoice_base_code = TaxCode(invoice_base_code.id)
    ...     invoice_base_code.amount
    Decimal('100000.00')
    >>> with config.set_context(periods=period_ids):
    ...     invoice_tax_code = TaxCode(invoice_tax_code.id)
    ...     invoice_tax_code.amount
    Decimal('21000.00')
    >>> with config.set_context(periods=period_ids):
    ...     credit_note_base_code = TaxCode(credit_note_base_code.id)
    ...     credit_note_base_code.amount
    Decimal('100000.00')
    >>> with config.set_context(periods=period_ids):
    ...     credit_note_tax_code = TaxCode(credit_note_tax_code.id)
    ...     credit_note_tax_code.amount
    Decimal('21000.00')

Test post without point of sale::

    >>> invoice, = invoice.duplicate()
    >>> invoice.pyafipws_concept
    '1'
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

Create empty invoice::

    >>> invoice = Invoice()
    >>> invoice.party = party
    >>> invoice.pos = pos
    >>> invoice.pyafipws_concept = '1'
    >>> invoice.invoice_type == invoice_types['1']
    True
    >>> invoice.payment_term = payment_term
    >>> invoice.click('post')
    >>> invoice.state
    'paid'

Create a paid invoice::

    >>> invoice = Invoice()
    >>> invoice.party = party
    >>> invoice.pos = pos
    >>> invoice.pyafipws_concept = '1'
    >>> invoice.payment_term = payment_term
    >>> line = invoice.lines.new()
    >>> line.product = product
    >>> line.quantity = 5
    >>> line.unit_price = Decimal('20000')
    >>> invoice.invoice_type == invoice_types['201']
    True
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
    >>> invoice.payment_term = payment_term
    >>> line = invoice.lines.new()
    >>> line.product = product
    >>> line.quantity = 5
    >>> line.unit_price = Decimal('20000')
    >>> line = invoice.lines.new()
    >>> line.type = 'comment'
    >>> line.description = 'Comment'
    >>> invoice.invoice_type == invoice_types['201']
    True
    >>> invoice.click('post')
    >>> credit = Wizard('account.invoice.credit', [invoice])
    >>> credit.form.with_refund = True
    >>> credit.execute('credit')
