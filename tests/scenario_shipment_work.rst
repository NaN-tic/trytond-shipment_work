======================
Shipment Work Scenario
======================

Imports::

    >>> import datetime
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from operator import attrgetter
    >>> from proteus import config, Model, Wizard, Report
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company
    >>> from trytond.modules.account.tests.tools import create_fiscalyear, \
    ...     create_chart, get_accounts, create_tax
    >>> from trytond.modules.account_invoice.tests.tools import \
    ...     set_fiscalyear_invoice_sequences, create_payment_term
    >>> today = datetime.date.today()

Create database::

    >>> config = config.set_trytond()
    >>> config.pool.test = True

Install shipment work::

    >>> Module = Model.get('ir.module')
    >>> module, = Module.find([('name', '=', 'shipment_work')])
    >>> module.click('install')
    >>> module, = Module.find([('name', '=', 'sale_price_list')])
    >>> module.click('install')
    >>> Wizard('ir.module.install_upgrade').execute('upgrade')

Create company::

    >>> _ = create_company()
    >>> company = get_company()

Reload the context::

    >>> User = Model.get('res.user')
    >>> Group = Model.get('res.group')
    >>> config._context = User.get_preferences(True, config.context)

Create fiscal year::

    >>> fiscalyear = set_fiscalyear_invoice_sequences(
    ...     create_fiscalyear(company))
    >>> fiscalyear.click('create_period')

Create chart of accounts::

    >>> _ = create_chart(company)
    >>> accounts = get_accounts(company)
    >>> revenue = accounts['revenue']
    >>> expense = accounts['expense']
    >>> cash = accounts['cash']

    >>> Journal = Model.get('account.journal')
    >>> cash_journal, = Journal.find([('type', '=', 'cash')])
    >>> cash_journal.credit_account = cash
    >>> cash_journal.debit_account = cash
    >>> cash_journal.save()

Create customer::

    >>> Party = Model.get('party.party')
    >>> customer = Party(name='Customer')
    >>> customer.save()

Create category::

    >>> ProductCategory = Model.get('product.category')
    >>> category = ProductCategory(name='Category')
    >>> category.save()

Create product::

    >>> ProductUom = Model.get('product.uom')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> hour, = ProductUom.find([('name', '=', 'Hour')])
    >>> ProductTemplate = Model.get('product.template')
    >>> Product = Model.get('product.product')
    >>> product = Product()
    >>> template = ProductTemplate()
    >>> template.name = 'product'
    >>> template.category = category
    >>> template.default_uom = unit
    >>> template.type = 'assets'
    >>> template.purchasable = True
    >>> template.salable = True
    >>> template.list_price = Decimal('10')
    >>> template.cost_price = Decimal('8')
    >>> template.cost_price_method = 'fixed'
    >>> template.account_expense = expense
    >>> template.account_revenue = revenue
    >>> template.save()
    >>> product.template = template
    >>> product.save()
    >>> hours_product = Product()
    >>> template = ProductTemplate()
    >>> template.name = 'product'
    >>> template.category = category
    >>> template.default_uom = hour
    >>> template.type = 'service'
    >>> template.purchasable = True
    >>> template.salable = True
    >>> template.list_price = Decimal('10')
    >>> template.cost_price = Decimal('8')
    >>> template.cost_price_method = 'fixed'
    >>> template.account_expense = expense
    >>> template.account_revenue = revenue
    >>> template.save()
    >>> hours_product.template = template
    >>> hours_product.save()

Create payment term::

    >>> payment_term = create_payment_term()
    >>> payment_term.save()

Create Employee::

    >>> Employee = Model.get('company.employee')
    >>> employee_party = Party(name='Employee')
    >>> employee_party.save()
    >>> employee = Employee(company=company, party=employee_party)
    >>> employee.save()

Configure shipment work::

    >>> Sequence = Model.get('ir.sequence')
    >>> StockConfig = Model.get('stock.configuration')
    >>> stock_config = StockConfig(1)
    >>> shipment_work_sequence, = Sequence.find([
    ...     ('code', '=', 'shipment.work'),
    ...     ])
    >>> stock_config.shipment_work_sequence = shipment_work_sequence
    >>> stock_config.shipment_work_hours_product = hours_product
    >>> stock_config.shipment_work_journal = cash_journal
    >>> stock_config.save()

Get locations::

    >>> Location = Model.get('stock.location')
    >>> warehouse, = Location.find([('type', '=', 'warehouse')])

Create a price List and assign it to customer::

    >>> PriceList = Model.get('product.price_list')
    >>> price_list = PriceList(name='Retail')
    >>> price_list_line = price_list.lines.new()
    >>> price_list_line.quantity = 10.0
    >>> price_list_line.product = product
    >>> price_list_line.formula = 'unit_price * 0.7'
    >>> price_list_line = price_list.lines.new()
    >>> price_list_line.product = product
    >>> price_list_line.formula = 'unit_price * 0.8'
    >>> price_list_line = price_list.lines.new()
    >>> price_list_line.formula = 'unit_price * 0.5'
    >>> price_list.save()
    >>> customer.sale_price_list = price_list
    >>> customer.save()

Create a shipment work with three lines::

    >>> Shipment = Model.get('shipment.work')
    >>> shipment = Shipment()
    >>> shipment.work_description = 'Work'
    >>> shipment.party = customer
    >>> shipment.click('pending')
    >>> shipment.number
    u'1'
    >>> shipment.state
    u'pending'
    >>> shipment.planned_date = today
    >>> shipment.employees.append(employee)
    >>> shipment.click('plan')
    >>> shipment.state
    u'planned'
    >>> shipment.done_description = 'Done'
    >>> shipment.click('done')
    >>> shipment.state
    u'done'
    >>> line = shipment.products.new()
    >>> line.description = 'Unkown product'
    >>> line.quantity = 1.0
    >>> line.unit = unit
    >>> line.quantity = 1.0
    >>> line.invoice_method
    u'invoice'
    >>> line = shipment.products.new()
    >>> line.product = product
    >>> line.quantity = 1.0
    >>> line.invoice_method = 'no_invoice'
    >>> line = shipment.products.new()
    >>> line.product = product
    >>> line.quantity = 2.0
    >>> line = shipment.products.new()
    >>> line.product = product
    >>> line.quantity = -2.0
    >>> shipment.warehouse = warehouse
    >>> shipment.save()

When the shipment work is checked an sale is created::

    >>> shipment.click('check')
    >>> shipment.state
    u'checked'
    >>> sale1, sale2 = shipment.sales
    >>> sale1.invoice_method == 'order'
    True
    >>> sale2.invoice_method == 'manual'
    True
    >>> sale1.payment_term == payment_term
    True
    >>> len(shipment.stock_moves) == 3
    True
    >>> sale1.untaxed_amount == Decimal('0.00')
    True
    >>> sale2.untaxed_amount == Decimal('8.00')
    True
