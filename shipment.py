# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import datetime
from decimal import Decimal
from itertools import izip
from sql import Null
from sql.aggregate import Sum

from trytond.model import Workflow, ModelSQL, ModelView, fields, Unique
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, If, Bool
from trytond.transaction import Transaction
from trytond.tools import grouped_slice, reduce_ids
from trytond import backend

__all__ = ['ShipmentWorkWorkRelation', 'ShipmentWorkEmployee', 'ShipmentWork',
    'TimesheetLine', 'ShipmentWorkProduct', 'StockMove']


class ShipmentWorkWorkRelation(ModelSQL):
    'ShipmentWork - Work'
    __name__ = 'shipment.work-timesheet.work'
    shipment = fields.Many2One('shipment.work', 'Shipment work',
        ondelete='CASCADE', required=True, select=True)
    work = fields.Many2One('timesheet.work', 'Work', required=True,
        select=True)

    @classmethod
    def __setup__(cls):
        super(ShipmentWorkWorkRelation, cls).__setup__()
        table = cls.__table__()
        cls._sql_constraints += [
            ('shipment_unique', Unique(table, table.shipment),
                'The shipment work must be unique.'),
            ('work_unique', Unique(table, table.work),
                'The work must be unique.'),
            ]


class ShipmentWorkEmployee(ModelSQL):
    'ShipmentWork - Employee'
    __name__ = 'shipment.work-company.employee'
    shipment = fields.Many2One('shipment.work', 'Shipment work',
        ondelete='CASCADE', required=True, select=True)
    employee = fields.Many2One('company.employee', 'Employee', required=True,
        select=True)


class ShipmentWork(Workflow, ModelSQL, ModelView):
    'Shipment Work'
    __name__ = 'shipment.work'
    _rec_name = 'number'

    company = fields.Many2One('company.company', 'Company', required=True,
        states={
            'readonly': Eval('state') != 'draft',
            },
        depends=['state'])
    number = fields.Char("Number", states={
            'readonly': Eval('state') != 'draft',
            }, depends=['state'])
    work = fields.One2One('shipment.work-timesheet.work', 'shipment', 'work',
        'Work',
        domain=[('company', '=', Eval('company'))],
        states={
            'readonly': Eval('state') != 'draft',
            },
        depends=['state', 'company'])
    party = fields.Many2One('party.party', 'Party', required=True,
        states={
            'readonly': Eval('state') != 'draft',
            },
        depends=['state'])
    planned_date = fields.Date('Planned Date',
        states={
            'required': ~Eval('state').in_(['draft', 'pending', 'cancel']),
            'readonly': Eval('state').in_(['cancel', 'done', 'checked']),
            },
        depends=['state'])
    done_date = fields.Date('Done Date',
        states={
            'readonly': Eval('state').in_(['done', 'checked', 'cancel']),
            },
        depends=['state'])
    work_description = fields.Text('Work Description',
        states={
            'readonly': Eval('state') != 'draft',
            },
        depends=['state'])
    done_description = fields.Text('Done Description',
        states={
            'readonly': Eval('state').in_(['done', 'checked', 'cancel']),
            'required': Eval('state').in_(['done', 'checked']),
            },
        depends=['state'])
    employees = fields.Many2Many('shipment.work-company.employee',
        'shipment', 'employee', 'Employees',
        states={
            'readonly': Eval('state').in_(['done', 'checked', 'cancel']),
            'required': Eval('state').in_(['planned', 'done', 'checked']),
            },
        domain=[('company', '=', Eval('company'))],
        depends=['state', 'company'])
    products = fields.One2Many('shipment.work.product', 'shipment', 'Products',
        states={
            'readonly': Eval('state').in_(['checked', 'cancel']),
            },
        context={
            'invoice_method': Eval('invoice_method'),
            },
        depends=['state', 'invoice_method'])
    timesheet_lines = fields.One2Many('timesheet.line', 'shipment',
        'Timesheet Lines',
        domain=[
            ('work', '=', Eval('work', 0)),
            ('company', '=', Eval('company')),
            ],
        states={
            'readonly': ~Bool(Eval('work')) | Eval('state').in_(
                ['checked', 'cancel']),
            },
        context={
            'invoice_method': Eval('timesheet_invoice_method'),
            },
        depends=['work', 'state', 'company', 'timesheet_invoice_method'])
    warehouse = fields.Many2One('stock.location', 'Warehouse',
        domain=[
            ('type', '=', 'warehouse'),
            ],
        states={
            'required': (Eval('state').in_(['done', 'checked']) &
                Bool(Eval('products', []))),
            'readonly': (Eval('state').in_(['checked', 'cancel']) |
                Bool(Eval('stock_moves', []))),
            },
        depends=['state'])
    payment_term = fields.Many2One('account.invoice.payment_term',
        'Payment Term', required=True,
        states={
            'readonly': Eval('state').in_(['checked', 'cancel']),
            },
        depends=['state'])
    state = fields.Selection([
            ('draft', 'Draft'),
            ('pending', 'Pending'),
            ('planned', 'Planned'),
            ('done', 'Done'),
            ('checked', 'Checked'),
            ('cancel', 'Canceled'),
            ], 'State', readonly=True)
    invoices = fields.Function(fields.One2Many('account.invoice', None,
            'Invoices'),
        'get_invoices', searcher='search_invoices')
    invoice_lines = fields.One2Many('account.invoice.line', 'origin',
        'Invoice Lines', readonly=True)
    planned_duration = fields.TimeDelta('Planned duration',
        'company_work_time',
        states={
            'readonly': Eval('state').in_(['done', 'checked', 'cancel']),
        },
        depends=['state'])
    total_hours = fields.Function(fields.TimeDelta('Total Hours',
            'company_work_time'),
        'get_total_hours')
    currency_digits = fields.Function(fields.Integer('Currency Digits'),
        'on_change_with_currency_digits')
    cost = fields.Function(fields.Numeric('Cost',
            digits=(16, Eval('currency_digits', 2)),
            depends=['currency_digits']),
        'get_cost')
    cost_cache = fields.Numeric('Cost Cache',
        digits=(16, Eval('currency_digits', 2)),
        readonly=True,
        depends=['currency_digits'])
    revenue = fields.Function(fields.Numeric('Revenue',
            digits=(16, Eval('currency_digits', 2)),
            depends=['currency_digits']),
        'get_cost')
    revenue_cache = fields.Numeric('Cost Cache',
        digits=(16, Eval('currency_digits', 2)),
        readonly=True,
        depends=['currency_digits'])

    invoice_method = fields.Selection([
            ('invoice', 'Invoice'),
            ('no_invoice', 'No Invoice'),
            ], 'Invoice method',
        states={
            'readonly': Eval('state').in_(['checked', 'cancel']),
        }, required=True)
    timesheet_invoice_method = fields.Selection([
            ('invoice', 'Invoice'),
            ('no_invoice', 'No Invoice'),
            ], 'Timesheet Invoice method',
        states={
            'readonly': Eval('state').in_(['checked', 'cancel']),
        }, required=True)
    customer_location = fields.Function(fields.Many2One('stock.location',
            'Customer Location'),
        'on_change_with_customer_location')
    stock_moves = fields.One2Many('stock.move', 'shipment', 'Stock Moves',
        domain=[
            ('from_location', 'child_of', [Eval('warehouse', -1)], 'parent'),
            ('to_location', '=', Eval('customer_location')),
            ('company', '=', Eval('company')),
            ], readonly=True,
        depends=['warehouse', 'customer_location', 'company'])
    origin = fields.Reference('Origin', selection='get_origin', states={
            'readonly': Eval('state') != 'draft',
            }, depends=['state'])

    @classmethod
    def __setup__(cls):
        super(ShipmentWork, cls).__setup__()

        cls._error_messages.update({
                'delete_cancel': ('Shipment Work "%s" must be cancelled before'
                    ' deletion.'),
                'invoice_not_canceled': ('Can not mark shipments as done '
                    'because its related the invoice "%s" can not be '
                    'canceled.'),
                'missing_shipment_sequence': ('There is no shipment work '
                    'sequence defined. Please define one in stock '
                    'configuration.'),
                'no_shipment_work_hours_product': ('There is no product '
                    'defined to invoice the timesheet lines. Please define one'
                    ' in stock configuration.'),
                'missing_payment_term': 'A payment term has not been defined.',
                'missing_account_receivable': (
                    'Party "%s" (%s) must have a receivable account.'),
                'missing_account_payable': (
                    'Party "%s" (%s) must have a payable account.'),
                'missing_journal': 'A default journal has not been defined.',
                'missing_address': (
                    'Party "%s" (%s) must have a default address.'),
                'missing_product_account': 'Product "%s" must have an account.'
                })
        cls._transitions |= set((
                ('draft', 'pending'),
                ('pending', 'planned'),
                ('planned', 'done'),
                ('done', 'checked'),
                ('draft', 'cancel'),
                ('pending', 'draft'),
                ('pending', 'cancel'),
                ('planned', 'cancel'),
                ('cancel', 'draft'),
                ))
        cls._buttons.update({
                'draft': {
                    'invisible': ~Eval('state').in_(['cancel', 'pending']),
                    'icon': If(Eval('state') == 'cancel', 'tryton-clear',
                        'tryton-go-previous'),
                    },
                'pending': {
                    'invisible': Eval('state') != 'draft',
                    'icon': 'tryton-ok',
                    },
                'plan': {
                    'invisible': Eval('state') != 'pending',
                    'icon': 'tryton-go-next',
                    },
                'done': {
                    'invisible': Eval('state') != 'planned',
                    'icon': 'tryton-ok',
                    },
                'check': {
                    'invisible': Eval('state') != 'done',
                    'icon': 'tryton-go-next',
                    },
                'cancel': {
                    'invisible': ~Eval('state').in_(['draft', 'pending',
                            'planned']),
                    'icon': 'tryton-cancel',
                    },
                })

    @classmethod
    def __register__(cls, module_name):
        pool = Pool()
        TimesheetWork = pool.get('timesheet.work')
        ShipmentWorkTimesheetWork = pool.get('shipment.work-timesheet.work')
        TableHandler = backend.get('TableHandler')

        sql_table = cls.__table__()
        timesheet_work = TimesheetWork.__table__()
        shipment_work_timesheet_work = ShipmentWorkTimesheetWork.__table__()
        table = TableHandler(cls, module_name)

        column_not_exists = not table.column_exist('number')

        super(ShipmentWork, cls).__register__(module_name)

        cursor = Transaction().connection.cursor()
        # Migration from 3.4: change hours into timedelta duration
        if table.column_exist('planned_hours'):
            cursor.execute(*sql_table.select(
                    sql_table.id, sql_table.planned_hours))
            for id_, hours in cursor.fetchall():
                if not hours:
                    continue
                duration = datetime.timedelta(hours=hours)
                cursor.execute(*sql_table.update(
                        [sql_table.planned_duration],
                        [duration],
                        where=sql_table.id == id_))
            table.drop_column('planned_hours')

        # Migration from 4.0: add number
        # TODO: Remove after upgrade 4.0 because can't install the module
        if column_not_exists:
            cursor.execute(*sql_table.update(
                    [sql_table.number],
                    [timesheet_work.name],
                    from_=[timesheet_work, shipment_work_timesheet_work],
                    where=(
                        (sql_table.id == shipment_work_timesheet_work.shipment)
                        & (shipment_work_timesheet_work.work
                            == timesheet_work.id))))

    @staticmethod
    def default_state():
        return 'draft'

    @staticmethod
    def default_invoice_method():
        return 'invoice'

    @staticmethod
    def default_timesheet_invoice_method():
        return 'invoice'

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @classmethod
    def default_payment_term(cls):
        PaymentTerm = Pool().get('account.invoice.payment_term')
        payment_terms = PaymentTerm.search(cls.payment_term.domain)
        if len(payment_terms) == 1:
            return payment_terms[0].id

    @classmethod
    def default_warehouse(cls):
        Location = Pool().get('stock.location')
        locations = Location.search(cls.warehouse.domain)
        if len(locations) == 1:
            return locations[0].id

    @classmethod
    def _get_origin(cls):
        'Return list of Model names for origin Reference'
        return []

    @classmethod
    def get_origin(cls):
        Model = Pool().get('ir.model')
        models = cls._get_origin()
        models = Model.search([
                ('model', 'in', models),
                ])
        return [(None, '')] + [(m.model, m.name) for m in models]

    def get_rec_name(self, name):
        res = self.number
        if self.party:
            res += ' - ' + self.party.rec_name
        return res

    @fields.depends('party')
    def on_change_with_customer_location(self, name=None):
        if self.party:
            return self.party.customer_location.id

    @fields.depends('currency')
    def on_change_with_currency_digits(self, name=None):
        Company = Pool().get('company.company')
        company = Company(Transaction().context.get('company'))

        if company.currency:
            return company.currency.digits
        return 2

    @fields.depends('party', 'payment_term')
    def on_change_party(self):
        if self.party:
            if self.party.customer_payment_term:
                self.payment_term = self.party.customer_payment_term
        if not self.payment_term:
            self.payment_term = self.default_payment_term()

    def get_invoices(self, name):
        invoices = set()
        for line in self.invoice_lines:
            if line.invoice:
                invoices.add(line.invoice.id)
        return list(invoices)

    @classmethod
    def search_invoices(cls, name, clause):
        return [
            ('products.invoice_lines.invoice',) + tuple(clause[1:]),
            ('timesheet_lines.invoice_lines.invoice',) + tuple(clause[1:]),
            ]

    @classmethod
    def _get_duration_query(cls, work_ids):
        'Returns the query to compute duration for works_ids'
        pool = Pool()
        Line = pool.get('timesheet.line')
        Relation = pool.get('shipment.work-timesheet.work')

        relation = Relation.__table__()
        line = Line.__table__()

        red_sql = reduce_ids(relation.shipment, work_ids)
        return relation.join(line,
                condition=(relation.work == line.work)
                ).select(relation.shipment, Sum(line.duration),
                where=red_sql,
                group_by=relation.shipment), line

    @classmethod
    def get_cost(cls, shipments, names):
        pool = Pool()
        Config = pool.get('stock.configuration')
        config = Config(1)
        if not config.shipment_work_hours_product:
            cls.raise_user_error('no_shipment_work_hours_product')
        product = config.shipment_work_hours_product

        result = {}
        for fname in ['cost', 'revenue']:
            result[fname] = {}

        for shipment in shipments:
            if shipment.cost_cache:
                result['cost'][shipment.id] = shipment.cost_cache
                result['revenue'][shipment.id] = shipment.revenue_cache
                continue

            cost = Decimal('0.00')
            revenue = Decimal('0.00')
            # shipment products
            for shipment_product in shipment.products:
                if not shipment_product.product:
                    continue
                cost += shipment_product.product.cost_price * \
                    Decimal(str(shipment_product.quantity))

                if shipment_product.invoice_method == 'no_invoice':
                    continue

                revenue += shipment_product.product.list_price * \
                    Decimal(str(shipment_product.quantity))

            # timesheet lines
            for line in shipment.timesheet_lines:
                cost += line.cost_price * Decimal(str(line.hours))
                if line.invoice_method == 'no_invoice':
                    continue
                revenue += product.list_price * Decimal(str(line.hours))

            result['cost'][shipment.id] = cost.quantize(
                Decimal(str(10.0 ** -2)))
            result['revenue'][shipment.id] = revenue.quantize(
                Decimal(str(10.0 ** -2)))

        return result

    @classmethod
    def get_total_hours(cls, works, name):
        cursor = Transaction().connection.cursor()

        work_ids = [w.id for w in works]
        hours = dict.fromkeys(work_ids, datetime.timedelta())
        for sub_ids in grouped_slice(work_ids):
            query, _ = cls._get_duration_query(sub_ids)
            cursor.execute(*query)
            hours.update(dict(cursor.fetchall()))
        return hours

    @classmethod
    def store_cache(cls, shipments):
        for shipment in shipments:
            cls.write([shipment], {
                    'cost_cache': shipment.cost,
                    'revenue_cache': shipment.revenue,
                    })

    @classmethod
    def restore_cache(cls, shipments):
        for shipment in shipments:
            cls.write([shipment], {
                    'cost_cache': None,
                    'revenue_cache': None,
                    })

    @classmethod
    def create(cls, vlist):
        pool = Pool()
        Config = pool.get('stock.configuration')
        Work = pool.get('timesheet.work')
        Sequence = pool.get('ir.sequence')

        config = Config(1)

        vlist = [x.copy() for x in vlist]
        works_to_create = []
        to_values = []
        all_values = []
        for values in vlist:
            if not values.get('number'):
                if not config.shipment_work_sequence:
                    cls.raise_user_error('missing_shipment_sequence')
                values['number'] = Sequence.get_id(
                    config.shipment_work_sequence.id)
            if not values.get('work'):
                works_to_create.append({
                        'name': values['number'],
                        })
                to_values.append(values)
            else:
                all_values.append(values)

        if works_to_create:
            works = Work.create(works_to_create)
            for values, work in izip(to_values, works):
                values['work'] = work.id
        return super(ShipmentWork, cls).create(all_values + to_values)

    @classmethod
    def copy(cls, shipments, default=None):
        if default is None:
            default = {}
        default['number'] = None
        default['work'] = None
        default['products'] = None
        default['timesheet_lines'] = None
        default['invoice_lines'] = None
        default['stock_moves'] = None
        default['done_description'] = None
        return super(ShipmentWork, cls).copy(shipments, default=default)

    @classmethod
    def delete(cls, shipments):
        pool = Pool()
        Work = pool.get('timesheet.work')
        cls.cancel(shipments)
        for shipment in shipments:
            if shipment.state != 'cancel':
                cls.raise_user_error('delete_cancel', (shipment.rec_name,))
        works = [s.work for s in shipments if s.work]
        super(ShipmentWork, cls).delete(shipments)
        Work.delete(works)

    @classmethod
    @ModelView.button
    @Workflow.transition('draft')
    def draft(cls, shipments):
        cls.restore_cache(shipments)
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('pending')
    def pending(cls, shipments):
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('planned')
    def plan(cls, shipments):
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('done')
    def done(cls, shipments):
        pool = Pool()
        Date = pool.get('ir.date')
        cls.write([s for s in shipments if not s.done_date], {
                'done_date': Date.today(),
                })
        cls.restore_cache(shipments)

    @classmethod
    @ModelView.button
    @Workflow.transition('checked')
    def check(cls, shipments):
        Move = Pool().get('stock.move')

        # TODO: create moves
        for shipment in shipments:
            shipment.create_moves()
        cls.save(shipments)
        Move.do([m for s in shipments for m in s.stock_moves])
        shipments_to_invoice = [x for x in shipments
            if (x.invoice_method != 'no_invoice' or
                x.timesheet_invoice_method != 'no_invoice')]
        cls.do_invoice(shipments_to_invoice)

    def create_moves(self):
        for shipment_product in self.products:
            move = shipment_product.get_move()
            if move:
                self.stock_moves += (move,)

    @classmethod
    def do_invoice(cls, shipments):
        pool = Pool()
        Invoice = pool.get('account.invoice')

        invoices_to_create = []
        for shipment in shipments:
            invoice_method = shipment.invoice_method
            timesheet_invoice_method = shipment.timesheet_invoice_method
            lines = []

            with Transaction().set_user(0, set_context=True):
                invoice = shipment.get_account_invoice(invoice_method)
                invoice.category = shipment.category

            # add shipment work products
            for product in shipment.products:
                if product.invoice_method == 'no_invoice':
                    continue
                line = shipment.get_product_invoice_line(
                        invoice, invoice_method, product)
                if line:
                    lines.append(line)

            # add timesheet lines
            hours = 0
            for timesheet_line in shipment.timesheet_lines:
                if timesheet_line.invoice_method == 'no_invoice':
                    continue
                hours += timesheet_line.hours
            if hours:
                line_hours = shipment.get_timesheet_invoice_line(
                            invoice, timesheet_invoice_method, hours)
                if line_hours:
                    lines.append(line_hours)

            if not lines:
                continue

            invoice.lines = lines
            invoice.on_change_taxes()
            invoices_to_create.append(invoice._save_values)

        if invoices_to_create:
            Invoice.create(invoices_to_create)

        cls.store_cache(shipments)

    @classmethod
    @ModelView.button
    @Workflow.transition('cancel')
    def cancel(cls, shipments):
        cls.store_cache(shipments)

    def get_account_invoice(self, invoice_method):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Config = pool.get('stock.configuration')
        AccountConfig = pool.get('account.configuration')

        config = Config(1)

        journal = config.shipment_work_journal
        if not journal:
            self.raise_user_error('missing_journal')

        party = self.party
        if party.account_receivable:
            account = party.account_receivable
        else:
            account_config = AccountConfig(1)
            if not account_config.default_account_receivable:
                self.raise_user_error('missing_account_receivable',
                    error_args=(party.name, party))
            account = account_config.default_account_receivable

        invoice = Invoice()
        invoice.type = 'out'
        invoice.company = self.company
        invoice.journal = journal
        invoice.account = account
        invoice.currency = self.company.currency
        invoice.party = party
        invoice.on_change_party()
        invoice.payment_term = self.payment_term
        invoice.invoice_date = self.done_date
        if not invoice.invoice_address:
            invoice.invoice_address = invoice.party.address_get()
        if not invoice.invoice_address:
            self.raise_user_error('missing_address',
                error_args=(party.name, party))
        return invoice

    def get_account_invoice_line(self, invoice, product, quantity):
        InvoiceLine = Pool().get('account.invoice.line')

        line = InvoiceLine()
        line.invoice = invoice
        line.currency = self.company.currency
        line.party = invoice.party
        line.quantity = quantity
        line.product = product
        line.type = 'line'
        line.sequence = 1
        line.on_change_product()

        if hasattr(line, 'unit_price'):
            line.unit_price = product.list_price
        if hasattr(line, 'gross_unit_price'):
            line.unit_price = product.list_price

        if not hasattr(line, 'account'):
            self.raise_user_error('missing_product_account',
                (product.rec_name,))
        return line

    def get_product_invoice_line(self, invoice, invoice_method,
            shipment_product):
        if (invoice_method == 'no_invoice' or
                shipment_product.invoice_method == 'no_invoice' or
                not shipment_product.product):
            return

        product = shipment_product.product
        quantity = shipment_product.quantity

        line = self.get_account_invoice_line(invoice, product, quantity)
        line.origin = self
        if shipment_product.description:
            line.description = shipment_product.description
        if not line.product:
            line.unit_price = Decimal('0.0')
        return line

    def get_timesheet_invoice_line(self, invoice, invoice_method, hours):
        pool = Pool()
        Config = pool.get('stock.configuration')

        if invoice_method == 'no_invoice' or hours <= Decimal(0):
            return

        config = Config(1)
        if not config.shipment_work_hours_product:
            self.raise_user_error('no_shipment_work_hours_product')
        product = config.shipment_work_hours_product
        line = self.get_account_invoice_line(invoice, product, hours)
        line.origin = self
        return line


class TimesheetLine:
    __name__ = 'timesheet.line'
    __metaclass__ = PoolMeta
    invoice_line = fields.Many2One('account.invoice.line', 'Invoice Line',
        readonly=True)
    shipment = fields.Many2One('shipment.work', 'Shipment Work')
    invoice_method = fields.Selection([
            ('invoice', 'Invoice'),
            ('no_invoice', 'No Invoice'),
            ], 'Invoice method', required=True)

    @staticmethod
    def default_invoice_method():
        return Transaction().context.get('invoice_method', 'invoice')


class ShipmentWorkProduct(ModelSQL, ModelView):
    'Shipment Product'
    __name__ = 'shipment.work.product'
    _rec_name = 'description'

    shipment = fields.Many2One('shipment.work', 'Shipment', required=True,
        ondelete='CASCADE')
    product = fields.Many2One('product.product', 'Product',
        domain=[
            ('type', '!=', 'service'),
            ])
    description = fields.Text('Description', required=True)
    quantity = fields.Float('Quantity', required=True,
        digits=(16, Eval('unit_digits', 2)),
        depends=['unit_digits'])
    unit = fields.Many2One('product.uom', 'Unit', required=True)
    unit_digits = fields.Function(fields.Integer('Unit Digits'),
        'on_change_with_unit_digits')
    invoice_lines = fields.One2Many('account.invoice.line', 'origin',
        'Invoice Lines', readonly=True)
    invoice_method = fields.Selection([
            ('invoice', 'Invoice'),
            ('no_invoice', 'No Invoice'),
            ], 'Invoice method', required=True)

    @staticmethod
    def default_invoice_method():
        return Transaction().context.get('invoice_method', 'invoice')

    @fields.depends('product', 'description', 'unit')
    def on_change_product(self):
        if self.product:
            category = self.product.default_uom.category
            if not self.unit or self.unit not in category.uoms:
                self.unit = self.product.default_uom.id
                self.unit.rec_name = self.product.default_uom.rec_name
                self.unit_digits = self.product.default_uom.digits
            if not self.description:
                self.description = self.product.rec_name

    @fields.depends('unit')
    def on_change_with_unit_digits(self, name=None):
        if self.unit:
            return self.unit.digits
        return 2

    def get_move(self):
        pool = Pool()
        Move = pool.get('stock.move')

        move = Move()
        move.product = self.product
        move.uom = self.unit
        move.quantity = self.quantity
        move.unit_price = self.product.list_price
        move.currency = self.shipment.company.currency
        move.from_location = self.shipment.warehouse.storage_location
        move.to_location = self.shipment.customer_location
        move.effective_date = self.shipment.done_date
        move.company = self.shipment.company
        move.origin = self
        move.state = 'draft'
        return move

    @classmethod
    def copy(cls, products, default=None):
        if default is None:
            default = {}
        default['invoice_lines'] = None
        return super(ShipmentWorkProduct, cls).copy(products, default=default)


class StockMove:
    __name__ = 'stock.move'
    __metaclass__ = PoolMeta

    @classmethod
    def __register__(cls, module_name):
        TableHandler = backend.get('TableHandler')
        handler = TableHandler(cls, module_name)
        table = cls.__table__()

        # Migration from 4.0: rename work_shipment into shipment_work
        if (handler.column_exist('work_shipment')
                and not handler.column_exist('number')):
            handler.column_rename('work_shipment', 'shipment_work')
        if handler.column_exist('shipment_work'):
            cursor = Transaction().connection.cursor()
            cursor.execute(*table.update(
                    [table.shipment],
                    ['shipment.work,%s' % table.shipment_work],
                    where=(table.shipment_work != Null)))
            handler.drop_column('shipment_work')

        super(StockMove, cls).__register__(module_name)

    @classmethod
    def _get_shipment(cls):
        models = super(StockMove, cls)._get_shipment()
        models.append('shipment.work')
        return models

    @classmethod
    def _get_origin(cls):
        models = super(StockMove, cls)._get_origin()
        models.append('shipment.work.product')
        return models
