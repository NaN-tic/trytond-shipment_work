# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import datetime
from decimal import Decimal
from itertools import izip
from sql import Null, Union
from sql.aggregate import Sum

from trytond.model import Workflow, ModelSQL, ModelView, fields, Unique
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, If, Bool
from trytond.transaction import Transaction
from trytond.tools import grouped_slice, reduce_ids
from trytond import backend
from collections import defaultdict

__all__ = ['ShipmentWorkWorkRelation', 'ShipmentWorkEmployee', 'ShipmentWork',
    'TimesheetLine', 'ShipmentWorkProduct', 'StockMove', 'Sale', 'SaleLine']


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
        'Payment Term',
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
            'Customer Location'), 'on_change_with_customer_location')
    storage_location = fields.Function(fields.Many2One('stock.location',
            'Storage Location'), 'on_change_with_storage_location')
    stock_moves = fields.One2Many('stock.move', 'shipment', 'Stock Moves',
        domain=[
            ('from_location', 'in', [
                Eval('customer_location'), Eval('storage_location')]),
            ('to_location', 'in', [
                Eval('customer_location'), Eval('storage_location')]),
            ('company', '=', Eval('company')),
            ], readonly=True,
        depends=['warehouse', 'customer_location', 'storage_location', 'company'])
    origin = fields.Reference('Origin', selection='get_origin', states={
            'readonly': Eval('state') != 'draft',
            }, depends=['state'])

    sales = fields.Function(fields.One2Many('sale.sale', None,
            'Sales'), 'get_sales', searcher='search_sales')
    sale_lines = fields.One2Many('sale.line', 'shipment_work',
        'Sale Line', readonly=True)

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
                'missing_product_account': 'Product "%s" must have an account.',
                'not_found_payment_term': 'Not found default Payment Term.',
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

    def get_sales(self, name):
        pool = Pool()
        Line = pool.get('sale.line')
        lines = Line.search(['OR',
                [('shipment_work_product', 'in', self.products)],
                [('shipment_work', '=', self.id)],
                ])
        return list(set([l.sale.id for l in lines]))

    @classmethod
    def search_sales(cls, name, clause):
        return ['OR',
            [tuple(('products.sale_lines.sale',)) + tuple(clause[1:])],
            [tuple(('sale_lines.sale',)) + tuple(clause[1:])],
            ]

    @fields.depends('party')
    def on_change_with_customer_location(self, name=None):
        if self.party:
            return self.party.customer_location.id

    @fields.depends('warehouse')
    def on_change_with_storage_location(self, name=None):
        if self.warehouse:
            return self.warehouse.storage_location.id

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
        default['stock_moves'] = None
        default['done_date'] = None
        default['done_description'] = None
        default['stock_moves'] = None
        default['sale_lines'] = None
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
        Date = Pool().get('ir.date')

        cls.write([s for s in shipments if not s.done_date], {
                'done_date': Date.today(),
                })
        cls.restore_cache(shipments)

    @classmethod
    @ModelView.button
    @Workflow.transition('checked')
    def check(cls, shipments):
        Move = Pool().get('stock.move')

        for shipment in shipments:
            shipment.create_moves()
        cls.save(shipments)
        Move.do([m for s in shipments for m in s.stock_moves])
        shipments_to_invoice = [x for x in shipments
            if (x.invoice_method != 'no_invoice' or
                x.timesheet_invoice_method != 'no_invoice')]

        cls.do_sale(shipments_to_invoice)

    def create_moves(self):
        for shipment_product in self.products:
            if not shipment_product.product:
                continue
            move = shipment_product.get_move()
            if move:
                self.stock_moves += (move,)

    def get_sale(self, invoice_method):
        Sale = Pool().get('sale.sale')

        sale = Sale()
        sale.company = self.work.company
        sale.currency = self.work.company.currency
        sale.warehouse = self.warehouse
        sale.payment_term = self.payment_term
        sale.payment_term = (self.payment_term or
            self.party.customer_payment_term)
        if not sale.payment_term:
            self.raise_user_error('not_found_payment_term')
        sale.party = self.party
        if hasattr(Sale, 'price_list') and self.party.sale_price_list:
            sale.price_list = self.party.sale_price_list
        sale.sale_date = self.done_date
        sale.invoice_address = self.party.address_get(type='invoice')
        sale.shipment_address = self.party.address_get(type='delivery')
        if invoice_method == 'invoice':
            sale.invoice_method = 'order'
        else:
            sale.invoice_method = 'manual'
        return sale

    @classmethod
    def do_sale(cls, shipments):
        Sale = Pool().get('sale.sale')

        sales_to_create = []
        for shipment in shipments:
            for invoice_method, _ in cls.invoice_method.selection:
                lines = []
                with Transaction().set_user(0, set_context=True):
                    sale = shipment.get_sale(invoice_method)
                for product in shipment.products:
                    line = product.get_sale_line(sale, invoice_method)
                    if line:
                        lines.append(line)
                lines += shipment.get_timesheet_sale_lines(invoice_method)
                if not lines:
                    continue
                sale.lines = lines
                sales_to_create.append(sale._save_values)
        if sales_to_create:
            Sale.create(sales_to_create)


    @classmethod
    @ModelView.button
    @Workflow.transition('cancel')
    def cancel(cls, shipments):
        cls.store_cache(shipments)

    @classmethod
    def _get_hours_query(cls, work_ids):
        'Returns the query to compute hours for works_ids'
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

    def get_timesheet_sale_lines(self, invoice_method):
        pool = Pool()
        SaleLine = pool.get('sale.line')
        Config = pool.get('stock.configuration')

        cursor = Transaction().connection.cursor()
        lines = []
        if invoice_method == 'no_invoice':
            return lines

        query, table = self._get_hours_query([self.id])
        query.where &= table.invoice_method == invoice_method
        cursor.execute(*query)
        hours_to_invoice = dict(cursor.fetchall()).get(self.id)
        if not hours_to_invoice:
            return lines

        config = Config(1)
        if not config.shipment_work_hours_product:
            self.raise_user_error('no_shipment_work_hours_product')
        sale_line = SaleLine()
        sale_line.shipment_work = self
        sale_line.quantity = Decimal(str(hours_to_invoice.total_seconds()/3600)
            ).quantize(Decimal(str(10.0 ** -2)))

        sale_line.product = config.shipment_work_hours_product
        sale_line.on_change_product()
        sale_line.shipment_work = self
        return [sale_line]


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

    def get_sale_line(self, sale, invoice_method):
        SaleLine = Pool().get('sale.line')

        if invoice_method != self.invoice_method:
            return

        sale_line = SaleLine()
        sale_line.sale = sale
        sale_line.quantity = self.quantity
        sale_line.unit = self.unit
        sale_line.description = self.description
        if self.product:
            sale_line.product = self.product
            sale_line.on_change_product()
        else:
            sale_line.unit_price = Decimal('0.0')
        sale_line.shipment_work_product = self
        return sale_line

    def get_move(self):
        Move = Pool().get('stock.move')

        if self.quantity >= 0:
            from_location = self.shipment.storage_location
            to_location = self.shipment.customer_location
        else:
            from_location = self.shipment.customer_location
            to_location = self.shipment.storage_location

        move = Move()
        move.product = self.product
        move.uom = self.unit
        move.quantity = abs(self.quantity)
        move.unit_price = self.product.list_price
        move.currency = self.shipment.company.currency
        move.from_location = from_location
        move.to_location = to_location
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


class Sale:
    __name__ = 'sale.sale'
    __metaclass__ = PoolMeta

    shipment_works = fields.Function(fields.One2Many('shipment.work', None,
            'Sales'), 'get_shipment_work', searcher='search_shipment_works')

    @classmethod
    def get_shipment_work(cls, sales, name):
        pool = Pool()
        SaleLine = pool.get('sale.line')
        WorkProduct = pool.get('shipment.work.product')
        table = SaleLine.__table__()
        line = SaleLine.__table__()
        work_product = WorkProduct.__table__()
        result = defaultdict(list)
        cursor = Transaction().cursor
        for sub_ids in grouped_slice([s.id for s in sales]):
            sub_ids = list(sub_ids)
            direct = table.select(table.sale,
                table.shipment_work.as_('shipment'),
                where=(table.shipment_work != Null) &
                reduce_ids(table.sale, sub_ids))
            indirect = line.join(work_product,
                condition=(work_product.id == line.shipment_work_product)
                ).select(line.sale, work_product.shipment.as_('shipment'),
                where=reduce_ids(line.sale, sub_ids))
            cursor.execute(*Union(direct, indirect))
            for sale, shipment in cursor.fetchall():
                result[sale].append(shipment)
        return result

    @classmethod
    def search_shipment_works(cls, name, clause):
        product_clause = [('lines.shipment_work_product.shipment',) +
            tuple(clause[1:])]
        direct_clause = [('lines.shipment_work',) + tuple(clause[1:])]
        return ['OR', product_clause, direct_clause]


class SaleLine:
    __name__ = 'sale.line'
    __metaclass__ = PoolMeta
    shipment_work_product = fields.Many2One('shipment.work.product',
        'Shipment Work Product')
    shipment_work = fields.Many2One('shipment.work',
        'Shipment Work')


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
