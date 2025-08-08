=========================
Invoice Supplier Scenario
=========================

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
    ...     get_tax_group
    >>> today = datetime.date.today()

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

Create fiscal year::

    >>> fiscalyear = set_fiscalyear_invoice_sequences(
    ...     create_fiscalyear(company))
    >>> fiscalyear.click('create_period')
    >>> period_ids = [p.id for p in fiscalyear.periods]

Create chart of accounts::

    >>> _ = create_chart(company)
    >>> accounts = get_accounts(company)
    >>> payable = accounts['payable']
    >>> revenue = accounts['revenue']
    >>> expense = accounts['expense']
    >>> account_tax = accounts['tax']

Create tax groups::

    >>> tax_group = get_tax_group('IVA', 'purchase')

Create tax::

    >>> TaxCode = Model.get('account.tax.code')
    >>> tax = create_tax(Decimal('.10'))
    >>> tax.iva_code = '5'
    >>> tax.group = tax_group
    >>> tax.save()
    >>> invoice_base_code = create_tax_code(tax, 'base', 'invoice')
    >>> invoice_base_code.save()
    >>> invoice_tax_code = create_tax_code(tax, 'tax', 'invoice')
    >>> invoice_tax_code.save()
    >>> credit_note_base_code = create_tax_code(tax, 'base', 'credit')
    >>> credit_note_base_code.save()
    >>> credit_note_tax_code = create_tax_code(tax, 'tax', 'credit')
    >>> credit_note_tax_code.save()

Create party::

    >>> Party = Model.get('party.party')
    >>> party = Party(name='Party',
    ...     iva_condition='responsable_inscripto',
    ...     vat_number='33333333339')
    >>> party.save()

Create account category::

    >>> ProductCategory = Model.get('product.category')
    >>> account_category = ProductCategory(name="Account Category")
    >>> account_category.accounting = True
    >>> account_category.account_expense = expense
    >>> account_category.account_revenue = revenue
    >>> account_category.supplier_taxes.append(tax)
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
    >>> line = payment_term.lines.new(type='remainder')
    >>> payment_term.save()

Create invoice::

    >>> Invoice = Model.get('account.invoice')
    >>> InvoiceLine = Model.get('account.invoice.line')
    >>> invoice = Invoice()
    >>> invoice.type = 'in'
    >>> invoice.party = party
    >>> invoice.payment_term = payment_term
    >>> invoice.invoice_date = today
    >>> invoice.tipo_comprobante = '001'
    >>> invoice.ref_pos_number = '1'
    >>> invoice.ref_voucher_number = '312'
    >>> line = InvoiceLine()
    >>> invoice.lines.append(line)
    >>> line.product = product
    >>> line.quantity = 5
    >>> line.unit_price = Decimal('20')
    >>> line = InvoiceLine()
    >>> invoice.lines.append(line)
    >>> line.account = expense
    >>> line.description = 'Test'
    >>> line.quantity = 1
    >>> line.unit_price = Decimal(10)
    >>> invoice.untaxed_amount
    Decimal('110.00')
    >>> invoice.tax_amount
    Decimal('10.00')
    >>> invoice.total_amount
    Decimal('120.00')
    >>> invoice.save()
    >>> invoice.reference
    '00001-00000312'
    >>> invoice.state
    'draft'
    >>> bool(invoice.move)
    False
    >>> invoice.click('validate_invoice')
    >>> invoice.state
    'validated'
    >>> bool(invoice.move)
    True
    >>> invoice.move.state
    'draft'
    >>> invoice.click('post')
    >>> invoice.state
    'posted'
    >>> bool(invoice.move)
    True
    >>> invoice.move.state
    'posted'
    >>> invoice.untaxed_amount
    Decimal('110.00')
    >>> invoice.tax_amount
    Decimal('10.00')
    >>> invoice.total_amount
    Decimal('120.00')
    >>> payable.reload()
    >>> payable.debit
    Decimal('0.00')
    >>> payable.credit
    Decimal('120.00')
    >>> expense.reload()
    >>> expense.debit
    Decimal('110.00')
    >>> expense.credit
    Decimal('0.00')
    >>> account_tax.reload()
    >>> account_tax.debit
    Decimal('10.00')
    >>> account_tax.credit
    Decimal('0.00')
    >>> with config.set_context(periods=period_ids):
    ...     invoice_base_code = TaxCode(invoice_base_code.id)
    ...     invoice_base_code.amount
    Decimal('100.00')
    >>> with config.set_context(periods=period_ids):
    ...     invoice_tax_code = TaxCode(invoice_tax_code.id)
    ...     invoice_tax_code.amount
    Decimal('10.00')
    >>> with config.set_context(periods=period_ids):
    ...     credit_note_base_code = TaxCode(credit_note_base_code.id)
    ...     credit_note_base_code.amount
    Decimal('0.00')
    >>> with config.set_context(periods=period_ids):
    ...     credit_note_tax_code = TaxCode(credit_note_tax_code.id)
    ...     credit_note_tax_code.amount
    Decimal('0.00')

Credit invoice::

    >>> credit = Wizard('account.invoice.credit', [invoice])
    >>> credit.form.with_refund = False
    >>> credit.form.invoice_date = invoice.invoice_date
    >>> credit.execute('credit')
    >>> credit_note, = Invoice.find(
    ...     [('type', '=', 'in'), ('id', '!=', invoice.id)])
    >>> credit_note.state
    'draft'
    >>> credit_note.untaxed_amount == -invoice.untaxed_amount
    True
    >>> credit_note.tax_amount == -invoice.tax_amount
    True
    >>> credit_note.total_amount == -invoice.total_amount
    True
    >>> credit_note.tipo_comprobante == '003'
    True
    >>> credit_note.reference
    >>> credit_note.ref_pos_number = '1'
    >>> credit_note.ref_voucher_number = '55'
    >>> credit_note.invoice_date = today
    >>> credit_note.click('validate_invoice')
    >>> credit_note.reference
    '00001-00000055'

Create a draft and post invoice::

    >>> invoice = Invoice()
    >>> invoice.type = 'in'
    >>> invoice.party = party
    >>> invoice.payment_term = payment_term
    >>> invoice.invoice_date = today
    >>> invoice.tipo_comprobante = '081'
    >>> invoice.ref_pos_number = '5'
    >>> invoice.ref_voucher_number = '333'
    >>> line = invoice.lines.new()
    >>> line.product = product
    >>> line.quantity = 1
    >>> line.unit_price = Decimal('20')
    >>> invoice.click('post')
    >>> invoice.reference
    '00005-00000333'

Credit invoice::

    >>> credit = Wizard('account.invoice.credit', [invoice])
    >>> credit.form.with_refund = False
    >>> credit.execute('credit')
    >>> credit_note, = Invoice.find(
    ...     [('type', '=', 'in'), ('state', '=', 'draft')])
    >>> credit_note.state
    'draft'
    >>> credit_note.untaxed_amount == -invoice.untaxed_amount
    True
    >>> credit_note.tax_amount == -invoice.tax_amount
    True
    >>> credit_note.total_amount == -invoice.total_amount
    True
    >>> credit_note.tipo_comprobante == '112'
    True
    >>> credit_note.reference

Create a posted and a draft invoice  to cancel::

    >>> invoice = Invoice()
    >>> invoice.type = 'in'
    >>> invoice.party = party
    >>> invoice.payment_term = payment_term
    >>> invoice.invoice_date = today
    >>> invoice.tipo_comprobante = '001'
    >>> invoice.ref_pos_number = '1'
    >>> invoice.ref_voucher_number = '123'
    >>> line = invoice.lines.new()
    >>> line.product = product
    >>> line.quantity = 1
    >>> line.unit_price = Decimal('20')
    >>> invoice.click('post')
    >>> invoice.reference
    '00001-00000123'
    >>> invoice_draft, = Invoice.duplicate([invoice])


Cancel draft invoice::

    >>> invoice_draft.tipo_comprobante
    >>> invoice_draft.reference
    >>> invoice_draft.click('cancel')
    >>> invoice_draft.state
    'cancelled'
    >>> invoice_draft.move
    >>> invoice_draft.reconciled

Cancel posted invoice::

    >>> invoice.click('cancel')
    >>> invoice.state
    'cancelled'
    >>> invoice.cancel_move is not None
    True
    >>> invoice.reconciled == today
    True
