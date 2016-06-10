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
    >>> hour, = ProductUom.find([('name', '=', 'Hour')])
    >>> Product = Model.get('product.product')
    >>> ProductTemplate = Model.get('product.template')
    >>> product = Product()
    >>> template = ProductTemplate()
    >>> template.name = 'Service'
    >>> template.default_uom = hour
    >>> template.type = 'service'
    >>> template.list_price = Decimal('20')
    >>> template.cost_price = Decimal('5')
    >>> template.account_revenue = revenue
    >>> template.save()
    >>> product.template = template
    >>> product.save()

Create payment term::

    >>> payment_term = create_payment_term()
    >>> payment_term.save()

Create Employee::

    >>> Employee = Model.get('company.employee')
    >>> employee_party = Party(name='Employee')
    >>> employee_party.save()
    >>> employee = Employee(company=company, party=employee_party)
    >>> employee.save()
    >>> user = User(1)
    >>> user.employees.append(employee)
    >>> user.employee = employee
    >>> user.save()
    >>> config._context = User.get_preferences(True, config.context)

Create a Project (Invoice Product Service)::

    >>> ProjectWork = Model.get('project.work')
    >>> project = ProjectWork()
    >>> project.name = 'Test Project'
    >>> project.type = 'project'
    >>> project.party = customer
    >>> project.project_invoice_method = 'progress'
    >>> project.product = product
    >>> project.effort_duration = datetime.timedelta(hours=1)
    >>> project.invoice_product_type = 'service'
    >>> project.save()

Configure shipment work::

    >>> Sequence = Model.get('ir.sequence')
    >>> StockConfig = Model.get('stock.configuration')
    >>> stock_config = StockConfig(1)
    >>> shipment_work_sequence, = Sequence.find([
    ...     ('code', '=', 'shipment.work'),
    ...     ])
    >>> stock_config.shipment_work_sequence = shipment_work_sequence
    >>> stock_config.save()

Create a shipment work with two lines::

    >>> Shipmentwork = Model.get('shipment.work')
    >>> Location = Model.get('stock.location')
    >>> swork = Shipmentwork()
    >>> swork.party = customer
    >>> swork.project = project
    >>> swork.planned_date = today
    >>> swork.work_description = 'Test Shipment Work'
    >>> employee = Employee(employee.id)
    >>> swork.employees.append(employee)
    >>> warehouse, = Location.find([('type', '=', 'warehouse')])
    >>> swork.warehouse = warehouse
    >>> swork.save()
    >>> swork.click('pending')
    >>> swork.state
    u'pending'
    >>> task1 = ProjectWork()
    >>> swork.tasks.append(task1)
    >>> task1.name = 'Test Task 1'
    >>> task1.type = 'task'
    >>> task1.invoice_product_type = 'service'
    >>> task1.parent = swork.shipment_work_project
    >>> task2 = ProjectWork()
    >>> swork.tasks.append(task2)
    >>> task2.name = 'Test Task 2'
    >>> task2.type = 'task'
    >>> task2.invoice_product_type = 'service'
    >>> task2.parent = swork.shipment_work_project
    >>> swork.click('plan')
    >>> swork.state
    u'planned'
    >>> swork.done_description = 'Shipment Work Done'
    >>> swork.click('done')
    >>> swork.state
    u'done'

Add Timesheet Work::

    >>> add = Wizard('shipment_work.shipment.work.timesheet', [swork])
    >>> add.form.duration = datetime.timedelta(0.01)
    >>> add.form.description = 'Demo description'
    >>> add.execute('handle')
    >>> add.state
    'end'

Create stock product::

    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> product = Product()
    >>> template = ProductTemplate()
    >>> template.name = 'Product'
    >>> template.default_uom = unit
    >>> template.type = 'goods'
    >>> template.list_price = Decimal('20')
    >>> template.cost_price = Decimal('8')
    >>> template.save()
    >>> product.template = template
    >>> product.save()

Get stock locations::

    >>> Location = Model.get('stock.location')
    >>> warehouse_loc, = Location.find([('code', '=', 'WH')])
    >>> supplier_loc, = Location.find([('code', '=', 'SUP')])
    >>> customer_loc, = Location.find([('code', '=', 'CUS')])
    >>> output_loc, = Location.find([('code', '=', 'OUT')])
    >>> storage_loc, = Location.find([('code', '=', 'STO')])

Create Stock Moves related with shipment work::

    >>> Move = Model.get('stock.move')
    >>> move = Move()
    >>> move.product = product
    >>> move.uom =unit
    >>> move.quantity = 1
    >>> move.from_location = output_loc
    >>> move.to_location = customer_loc
    >>> move.company = company
    >>> move.unit_price = Decimal('1')
    >>> move.currency = company.currency
    >>> swork.stock_moves.append(move)
    >>> swork.save()

Check shipment work::

    >>> swork.click('check')
    >>> swork.state
    u'checked'
    >>> swork.reload()
    >>> move, = swork.stock_moves
    >>> move.shipment.state
    u'done'
