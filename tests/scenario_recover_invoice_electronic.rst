========================
Recover Invoice Scenario
========================

Imports::
    >>> import datetime as dt
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from operator import attrgetter
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
    ...     create_pos, get_pos, get_invoice_types, get_tax, get_wsfev1
    >>> from trytond.modules.party_ar.tests.tools import set_afip_certs
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

Configure AFIP certificates::

    >>> _ = set_afip_certs(company=company)

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
    >>> account_revenue = accounts['revenue']
    >>> account_expense = accounts['expense']
    >>> account_cash = accounts['cash']

Create point of sale::

    >>> _ = create_pos(company, type='electronic', number=4000, ws='wsfe')
    >>> pos = get_pos(type='electronic', number=4000)
    >>> invoice_types = get_invoice_types(pos=pos)

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
    >>> party.vat_number='30688555872'
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

SetUp webservice AFIP::

    >>> wsfev1 = get_wsfev1(company, config)

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
    >>> invoice.pyafipws_concept = '1'
    >>> invoice.click('post')

Duplicate and test recover last invoice::

    >>> last_cbte_nro = int(wsfev1.CompUltimoAutorizado('1', pos.number))
    >>> recover_invoice, = invoice.duplicate()
    >>> recover_invoice.pyafipws_concept
    '1'
    >>> recover_invoice.pyafipws_cae
    >>> recover_invoice.pyafipws_cae_due_date
    >>> recover_invoice.pos
    >>> recover_invoice.invoice_type
    >>> recover_invoice.transactions
    []
    >>> recover = Wizard('account.invoice.recover')
    >>> recover.form.pos = invoice.pos
    >>> recover.form.invoice_type = invoice.invoice_type
    >>> recover.form.cbte_nro = last_cbte_nro
    >>> recover.execute('ask_afip')
    >>> recover.state
    'ask_afip'
    >>> recover.form.invoice = recover_invoice
    >>> recover.form.CbteNro == str(last_cbte_nro)
    True
    >>> recover.form.CAE == invoice.pyafipws_cae
    True
    >>> recover.execute('save_invoice')
    >>> recover_invoice.reload()
    >>> recover_invoice.state
    'posted'
    >>> bool(recover_invoice.move)
    True
    >>> recover_invoice.invoice_date == invoice.invoice_date
    True
    >>> recover_invoice.pos == invoice.pos
    True
    >>> recover_invoice.invoice_type == invoice.invoice_type
    True
    >>> recover_invoice.number == invoice.number
    True
    >>> recover_invoice.pyafipws_cae == invoice.pyafipws_cae
    True
