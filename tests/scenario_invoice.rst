================
Invoice Scenario
================

Imports::
    >>> import datetime as dt
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from proteus import Model, Wizard
    >>> from trytond.tests.tools import activate_modules
    >>> from trytond.modules.currency.tests.tools import get_currency
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company
    >>> from trytond.modules.account.tests.tools import create_fiscalyear, \
    ...     create_chart
    >>> from trytond.modules.account_ar.tests.tools import get_accounts
    >>> from trytond.modules.account_invoice.tests.tools import \
    ...     set_fiscalyear_invoice_sequences
    >>> from trytond.modules.account_invoice_ar.tests.tools import \
    ...     create_pos, get_pos, get_invoice_types, get_tax
    >>> today = dt.date.today()

Install account_invoice_ar::

    >>> config = activate_modules('account_invoice_ar')

Create company::

    >>> currency = get_currency('ARS')
    >>> currency.afip_code = 'PES'
    >>> currency.save()
    >>> _ = create_company(currency=currency)
    >>> company = get_company()
    >>> tax_identifier = company.party.identifiers.new()
    >>> tax_identifier.type = 'ar_vat'
    >>> tax_identifier.code = '30710158254' # gcoop CUIT
    >>> company.party.iva_condition = 'responsable_inscripto'
    >>> company.party.save()

Create fiscal year::

    >>> fiscalyear = set_fiscalyear_invoice_sequences(
    ...     create_fiscalyear(company))
    >>> fiscalyear.click('create_period')
    >>> period = fiscalyear.periods[0]
    >>> period_ids = [p.id for p in fiscalyear.periods]

Create chart of accounts::

    >>> _ = create_chart(company, chart='account_ar.root_ar')
    >>> accounts = get_accounts(company)
    >>> account_receivable = accounts['receivable']
    >>> account_payable = accounts['payable']
    >>> account_revenue = accounts['revenue']
    >>> account_expense = accounts['expense']
    >>> account_tax = accounts['sale_tax']
    >>> account_cash = accounts['cash']

Create point of sale::

    >>> _ = create_pos(company)
    >>> pos = get_pos()
    >>> invoice_types = get_invoice_types()

Create taxes::

    >>> sale_tax = get_tax('IVA Ventas 21%')
    >>> sale_tax_nogravado = get_tax('IVA Ventas No Gravado')

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
    >>> writeoff_method.credit_account = account_expense
    >>> writeoff_method.debit_account = account_expense
    >>> writeoff_method.save()

Create party::

    >>> Party = Model.get('party.party')
    >>> party = Party(name='Party')
    >>> party.iva_condition='responsable_inscripto'
    >>> party.vat_number='33333333339'
    >>> party.account_receivable = account_receivable
    >>> party.save()

Create party consumidor final::

    >>> Party = Model.get('party.party')
    >>> party_cf = Party(name='Party')
    >>> party_cf.iva_condition='consumidor_final'
    >>> party.account_receivable = account_receivable
    >>> party_cf.save()

Create account category::

    >>> ProductCategory = Model.get('product.category')
    >>> account_category = ProductCategory(name="Account Category")
    >>> account_category.accounting = True
    >>> account_category.account_expense = account_expense
    >>> account_category.account_revenue = account_revenue
    >>> account_category.customer_taxes.append(sale_tax)
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
    >>> line.account = account_revenue
    >>> line.taxes.append(sale_tax_nogravado)
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
    >>> bool(invoice.has_report_cache)
    False

Test change tax::

    >>> tax_line = invoice.taxes[0]
    >>> tax_line.tax == sale_tax
    True
    >>> tax_line.tax = None
    >>> tax_line.tax = sale_tax

Post invoice::

    >>> invoice.click('post')
    >>> invoice.state
    'posted'
    >>> invoice.tax_identifier.code
    '30710158254'
    >>> bool(invoice.has_report_cache)
    True
    >>> invoice.untaxed_amount
    Decimal('220.00')
    >>> invoice.tax_amount
    Decimal('42.00')
    >>> invoice.total_amount
    Decimal('262.00')
    >>> account_receivable.reload()
    >>> account_receivable.debit
    Decimal('262.00')
    >>> account_receivable.credit
    Decimal('0.00')
    >>> account_revenue.reload()
    >>> account_revenue.debit
    Decimal('0.00')
    >>> account_revenue.credit
    Decimal('220.00')
    >>> account_tax.reload()
    >>> account_tax.debit
    Decimal('0.00')
    >>> account_tax.credit
    Decimal('42.00')

Credit invoice with refund::

    >>> credit = Wizard('account.invoice.credit', [invoice])
    >>> credit.form.with_refund = True
    >>> credit.form.invoice_date = invoice.invoice_date
    >>> credit.execute('credit')
    >>> invoice.reload()
    >>> invoice.state
    'cancelled'
    >>> bool(invoice.reconciled)
    True
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
    >>> credit_note.invoice_type == invoice_types['3']
    True
    >>> invoice.reload()
    >>> invoice.state
    'cancelled'
    >>> invoice.reconciled == today
    True
    >>> account_receivable.reload()
    >>> account_receivable.debit
    Decimal('262.00')
    >>> account_receivable.credit
    Decimal('262.00')
    >>> account_revenue.reload()
    >>> account_revenue.debit
    Decimal('220.00')
    >>> account_revenue.credit
    Decimal('220.00')
    >>> account_tax.reload()
    >>> account_tax.debit
    Decimal('42.00')
    >>> account_tax.credit
    Decimal('42.00')

Attempt to post invoice without pos::

    >>> invoice, = invoice.duplicate()
    >>> invoice.state
    'draft'
    >>> invoice.click('post')  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    UserError: ...
    >>> invoice.state
    'draft'

Pay invoice::

    >>> invoice.pos = pos
    >>> invoice.invoice_type == invoice_types['1']
    True
    >>> invoice.click('post')

    >>> pay = Wizard('account.invoice.pay', [invoice])
    >>> pay.form.amount
    Decimal('262.00')
    >>> pay.form.amount = Decimal('120.00')
    >>> pay.form.payment_method = payment_method
    >>> pay.execute('choice')
    >>> pay.state
    'end'

    >>> pay = Wizard('account.invoice.pay', [invoice])
    >>> pay.form.amount
    Decimal('120.00')
    >>> pay.form.amount = Decimal('42.00')
    >>> pay.form.payment_method = payment_method
    >>> pay.execute('choice')
    >>> pay.form.type = 'partial'
    >>> pay.form.amount
    Decimal('42.00')
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
    Decimal('-20.00')
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
    [Decimal('1.00'), Decimal('42.00'), Decimal('99.00'), Decimal('120.00')]

Create empty invoice::

    >>> invoice = Invoice()
    >>> invoice.party = party
    >>> invoice.pos = pos
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

Clear company tax_identifier::

    >>> tax_identifier, = company.party.identifiers
    >>> tax_identifier.type = None
    >>> tax_identifier.save()

Create a paid invoice::

    >>> invoice = Invoice()
    >>> invoice.party = party
    >>> invoice.pos = pos
    >>> invoice.payment_term = payment_term
    >>> line = invoice.lines.new()
    >>> line.product = product
    >>> line.quantity = 5
    >>> line.unit_price = Decimal('40')

    >>> invoice.click('post')  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    UserError: ...
    >>> invoice.state
    'draft'

    >>> tax_identifier, = company.party.identifiers
    >>> tax_identifier.type = 'ar_vat'
    >>> tax_identifier.save()

    >>> invoice.click('post')
    >>> pay = Wizard('account.invoice.pay', [invoice])
    >>> pay.form.payment_method = payment_method
    >>> pay.execute('choice')
    >>> pay.state
    'end'
    >>> invoice.tax_identifier.type
    'ar_vat'
    >>> invoice.state
    'paid'

The invoice is posted when the reconciliation is deleted::

    >>> invoice.payment_lines[0].reconciliation.delete()
    >>> invoice.reload()
    >>> invoice.state
    'posted'
    >>> invoice.tax_identifier.type
    'ar_vat'

Credit invoice with non line lines::

    >>> invoice = Invoice()
    >>> invoice.party = party
    >>> invoice.pos = pos
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
