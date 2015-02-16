# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from sql.aggregate import Sum
from itertools import izip
from decimal import Decimal

from trytond.model import Workflow, ModelSQL, ModelView, Model, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, If, Bool
from trytond.transaction import Transaction
from trytond.tools import grouped_slice, reduce_ids

__all__ = ['Configuration', 'ConfigurationCompany', 'ShipmentWorkWorkRelation',
    'ShipmentWorkEmployee', 'ShipmentWork', 'TimesheetLine',
    'ShipmentWorkProduct', 'SaleLine', 'StockMove']
__metaclass__ = PoolMeta


class Configuration:
    __name__ = 'stock.configuration'

    shipment_work_sequence = fields.Function(fields.Many2One('ir.sequence',
            'Shipment Work Sequence',
            domain=[
                ('company', 'in',
                    [Eval('context', {}).get('company', -1), None]),
                ('code', '=', 'shipment.work'),
                ], required=True),
        'get_company_config', 'set_company_config')

    shipment_work_hours_product = fields.Function(fields.Many2One(
            'product.product', 'Shipment Work Hours Product',
            help='The product used to invoice the service hours of a shipment',
            domain=[
                ('type', '=', 'service'),
                ('salable', '=', True),
                ]),
        'get_company_config', 'set_company_config')

    @classmethod
    def get_company_config(self, configs, names):
        pool = Pool()
        CompanyConfig = pool.get('stock.configuration.company')

        company_id = Transaction().context.get('company')
        company_configs = CompanyConfig.search([
                ('company', '=', company_id),
                ])

        res = {}
        for fname in names:
            res[fname] = {
                configs[0].id: None,
                }
            if company_configs:
                val = getattr(company_configs[0], fname)
                if isinstance(val, Model):
                    val = val.id
                res[fname][configs[0].id] = val
        return res

    @classmethod
    def set_company_config(self, configs, name, value):
        pool = Pool()
        CompanyConfig = pool.get('stock.configuration.company')

        company_id = Transaction().context.get('company')
        company_configs = CompanyConfig.search([
                ('company', '=', company_id),
                ])
        if company_configs:
            company_config = company_configs[0]
        else:
            company_config = CompanyConfig(company=company_id)
        setattr(company_config, name, value)
        company_config.save()


class ConfigurationCompany(ModelSQL):
    'Stock Configuration per Company'
    __name__ = 'stock.configuration.company'

    company = fields.Many2One('company.company', 'Company', required=True,
        ondelete='CASCADE', select=True)
    shipment_work_sequence = fields.Many2One('ir.sequence',
        'Shipment Work Sequence',
        domain=[
            ('company', 'in', [Eval('company', -1), None]),
            ('code', '=', 'shipment.work'),
            ],
        depends=['company'])
    shipment_work_hours_product = fields.Many2One('product.product',
        'Shipment Work Hours Product',
        domain=[
            ('type', '=', 'service'),
            ])


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
        cls._sql_constraints += [
            ('shipment_unique', 'UNIQUE(shipment)',
                'The shipment work must be unique.'),
            ('work_unique', 'UNIQUE(work)',
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
    _rec_name = 'work_name'

    company = fields.Many2One('company.company', 'Company', required=True,
        select=True, states={
            'readonly': Eval('state') != 'draft',
            },
        depends=['state'])
    work_name = fields.Function(fields.Char('Code', required=True,
            readonly=True),
        'get_work_name', searcher='search_work_name', setter='set_work_name')
    work = fields.One2One('shipment.work-timesheet.work', 'shipment', 'work',
        'Work',
        domain=[('company', '=', Eval('company'))],
        states={
            'readonly': Eval('state') != 'draft',
            },
        depends=['state', 'company'])
    party = fields.Many2One('party.party', 'Party', required=True, select=True,
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
            'required': (Eval('state').in_(['checked']) &
                (Bool(Eval('products', [])) | Bool(Eval('total_hours')))),
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
            ], 'State', readonly=True, select=True)
    sales = fields.Function(fields.One2Many('sale.sale', None,
            'Sales'), 'get_sales')
    planned_hours = fields.Float('Planned Hours', digits=(16, 2),
        states={
            'readonly': Eval('state').in_(['done', 'checked', 'cancel']),
        },
        depends=['state'])
    total_hours = fields.Function(fields.Float('Total Hours',
            digits=(16, 2)),
        'get_total_hours')
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
    warehouse_output = fields.Function(fields.Many2One('stock.location',
            'Warehouse Output'), 'on_change_with_warehouse_output')
    stock_moves = fields.One2Many('stock.move', 'work_shipment',
        'Stock Moves',
        domain=[
            ('from_location', '=', Eval('warehouse_output')),
            ('to_location', '=', Eval('customer_location')),
            ('company', '=', Eval('company')),
            ],
        add_remove=[
            ('state', '=', 'draft'),
            ('work_shipment', '=', None),
            ],
        states={
            'readonly': Eval('state').in_(['checked', 'cancel']),
            },
        depends=['customer_location', 'warehouse_output', 'state', 'company'])

    @classmethod
    def __setup__(cls):
        super(ShipmentWork, cls).__setup__()
        cls._error_messages.update({
                'delete_cancel': ('Shipment Work "%s" must be cancelled before'
                    ' deletion.'),
                'missing_shipment_sequence': ('There is no shipment work '
                    'sequence defined. Please define one in stock '
                    'configuration.'),
                'no_shipment_work_hours_product': ('There is no product '
                    'defined to invoice the timesheet lines. Please define one'
                    ' in stock configuration.'),

                })
        cls._transitions |= set((
                ('draft', 'pending'),
                ('pending', 'draft'),
                ('pending', 'planned'),
                ('planned', 'done'),
                ('done', 'checked'),
                ('draft', 'cancel'),
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

    @fields.depends('party')
    def on_change_with_customer_location(self, name=None):
        if self.party:
            return self.party.customer_location.id

    @fields.depends('warehouse')
    def on_change_with_warehouse_output(self, name=None):
        if self.warehouse:
            return self.warehouse.output_location.id

    @fields.depends('party', 'payment_term')
    def on_change_party(self):
        changes = {}
        payment_term = None
        if self.party:
            if self.party.customer_payment_term:
                payment_term = self.party.customer_payment_term
        if payment_term:
            changes['payment_term'] = payment_term.id
            changes['payment_term.rec_name'] = payment_term.rec_name
        else:
            changes['payment_term'] = self.default_payment_term()
        return changes

    def get_work_name(self, name):
        if not self.work:
            return ''
        return self.work.name

    def get_sales(self, name):
        pool = Pool()
        Line = pool.get('sale.line')
        lines = Line.search(['OR',
                [('shipment_work_product', 'in', self.products)],
                [('shipment_work', '=', self.id)],
                ])
        return list(set([l.sale.id for l in lines]))

    @classmethod
    def search_work_name(cls, name, clause):
        return [('work.name',) + tuple(clause[1:])]

    @classmethod
    def set_work_name(cls, works, name, value):
        Work = Pool().get('timesheet.work')
        Work.write([p.work for p in works if p.work], {
                'name': value,
                })

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
                ).select(relation.shipment, Sum(line.hours),
                where=red_sql,
                group_by=relation.shipment), line

    @classmethod
    def get_total_hours(cls, works, name):
        cursor = Transaction().cursor

        work_ids = [w.id for w in works]
        hours = dict.fromkeys(work_ids, 0)
        for sub_ids in grouped_slice(work_ids):
            query, _ = cls._get_hours_query(sub_ids)
            cursor.execute(*query)
            hours.update(dict(cursor.fetchall()))
        return hours

    @classmethod
    def create(cls, vlist):
        pool = Pool()
        Config = pool.get('stock.configuration')
        Work = pool.get('timesheet.work')
        Sequence = pool.get('ir.sequence')
        config = Config(1)
        vlist = [x.copy() for x in vlist]
        to_create = []
        to_values = []
        all_values = []
        for values in vlist:
            if not values.get('work'):
                if not config.shipment_work_sequence:
                    cls.raise_user_error('missing_shipment_sequence')
                code = Sequence.get_id(config.shipment_work_sequence.id)
                to_create.append({
                        'name': code,
                        })
                to_values.append(values)
            else:
                all_values.append(values)
        if to_create:
            works = Work.create(to_create)
            for values, work in izip(to_values, works):
                values['work'] = work.id
        return super(ShipmentWork, cls).create(all_values + to_values)

    @classmethod
    def copy(cls, shipments, defaults=None):
        if defaults is None:
            defaults = {}
        defaults.setdefault('work')
        defaults.setdefault('work_name')
        defaults.setdefault('timesheet_lines', [])
        defaults.setdefault('stock_moves', [])
        new_shipments = super(ShipmentWork, cls).copy(shipments, defaults)
        return new_shipments

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

    @classmethod
    @ModelView.button
    @Workflow.transition('checked')
    def check(cls, shipments):
        pool = Pool()
        ShipmentOut = pool.get('stock.shipment.out')
        Sale = pool.get('sale.sale')
        sales_to_create = []
        shipments_to_create = []
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
            stock_shipment = shipment.get_stock_shipment()
            if stock_shipment:
                shipments_to_create.append(stock_shipment._save_values)
        if sales_to_create:
            Sale.create(sales_to_create)
        if shipments_to_create:
            stock_shipments = ShipmentOut.create(shipments_to_create)
            ShipmentOut.wait(stock_shipments)
            ShipmentOut.assign(stock_shipments)
            ShipmentOut.pack(stock_shipments)
            ShipmentOut.done(stock_shipments)

    @classmethod
    @ModelView.button
    @Workflow.transition('cancel')
    def cancel(cls, shipments):
        pass

    def get_sale(self, invoice_method):
        pool = Pool()
        Sale = pool.get('sale.sale')
        sale = Sale()
        sale.company = self.work.company
        sale.currency = self.work.company.currency
        sale.warehouse = self.warehouse
        sale.payment_term = self.payment_term
        sale.party = self.party
        sale.sale_date = None
        sale.invoice_address = self.party.address_get(type='invoice')
        sale.shipment_address = self.party.address_get(type='delivery')
        if invoice_method == 'invoice':
            sale.invoice_method = 'order'
        else:
            sale.invoice_method = 'manual'
        return sale

    def get_stock_shipment(self):
        pool = Pool()
        ShipmentOut = pool.get('stock.shipment.out')
        if not self.stock_moves:
            return
        shipment = ShipmentOut()
        shipment.company = self.work.company
        shipment.warehoues = self.warehouse
        shipment.customer = self.party
        shipment.planned_date = self.planned_date
        shipment.effective_date = self.done_date
        shipment.delivery_address = self.party.address_get(type='delivery')
        shipment.reference = self.work_name
        shipment.moves = self.stock_moves
        shipment.state = 'draft'
        return shipment

    def get_timesheet_sale_lines(self, invoice_method):
        pool = Pool()
        SaleLine = pool.get('sale.line')
        Config = pool.get('stock.configuration')
        cursor = Transaction().cursor
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
        sale_line.quantity = hours_to_invoice
        sale_line.product = config.shipment_work_hours_product
        for key, value in sale_line.on_change_product().iteritems():
            setattr(sale_line, key, value)
        sale_line.shipment_work = self
        return [sale_line]


class TimesheetLine:
    __name__ = 'timesheet.line'

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
    sale_lines = fields.One2Many('sale.line', 'shipment_work_product',
        'Sale Line', readonly=True)
    invoice_method = fields.Selection([
            ('invoice', 'Invoice'),
            ('no_invoice', 'No Invoice'),
            ], 'Invoice method', required=True)

    @staticmethod
    def default_invoice_method():
        return Transaction().context.get('invoice_method', 'invoice')

    @fields.depends('product', 'description', 'unit')
    def on_change_product(self):
        changes = {}
        if not self.product:
            return changes
        category = self.product.default_uom.category
        if not self.unit or self.unit not in category.uoms:
            changes['unit'] = self.product.default_uom.id
            changes['unit.rec_name'] = self.product.default_uom.rec_name
            changes['unit_digits'] = self.product.default_uom.digits
        if not self.description:
            changes['description'] = self.product.rec_name
        return changes

    @fields.depends('unit')
    def on_change_with_unit_digits(self, name=None):
        if self.unit:
            return self.unit.digits
        return 2

    def get_sale_line(self, sale, invoice_method):
        pool = Pool()
        if invoice_method != self.invoice_method:
            return
        SaleLine = pool.get('sale.line')
        sale_line = SaleLine()
        sale_line.sale = sale
        sale_line.quantity = self.quantity
        sale_line.unit = self.unit
        sale_line.description = self.description
        if self.product:
            sale_line.product = self.product
            for key, value in sale_line.on_change_product().iteritems():
                setattr(sale_line, key, value)
        else:
            sale_line.unit_price = Decimal('0.0')
        sale_line.shipment_work_product = self
        return sale_line


class SaleLine:
    __name__ = 'sale.line'
    shipment_work_product = fields.Many2One('shipment.work.product',
        'Shipment Work Product')
    shipment_work = fields.Many2One('shipment.work',
        'Shipment Work')


class StockMove:
    __name__ = 'stock.move'

    work_shipment = fields.Many2One('shipment.work', 'Shipment Work')
