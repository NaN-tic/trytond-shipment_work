# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import datetime

from trytond.model import Workflow, ModelSQL, ModelView, fields
from trytond.wizard import Wizard, StateAction, StateView, StateTransition, Button
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, If, Bool
from trytond.transaction import Transaction
from trytond.pyson import PYSONEncoder
from trytond import backend
from trytond.modules.project_invoice.work import INVOICE_METHODS

__all__ = ['ShipmentWorkEmployee', 'ShipmentWork',
    'ShipmentWorkTimesheetAsk', 'ShipmentWorkTimesheet',
    'ShipmentWorkOpenTimesheetLine', 'ProjectWork', 'TimesheetLine',
    'StockMove']


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

    number = fields.Char('Number', required=True,
            readonly=True)
    company = fields.Many2One('company.company', 'Company', required=True,
        select=True, states={
            'readonly': Eval('state') != 'draft',
            },
        depends=['state'])
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
    project = fields.Many2One('project.work', 'Project', required=True,
        states={
            'readonly': Eval('state') != 'draft',
            },
        domain=[
            ('parent', '=', None),
            ('type', '=', 'project'),
            ('party', '=', Eval('party')),
            ],
        depends=['state', 'party'])
    shipment_work_project = fields.Many2One('project.work', 'Shipment Work Project',
        states={
            'readonly': Eval('state') != 'draft',
            },
        domain=[
            ('parent', '=', Eval('project')),
            ('type', '=', 'project'),
            ('party', '=', Eval('party')),
            ],
        depends=['state', 'project', 'party'])
    tasks = fields.One2Many('project.work', 'shipment_work', 'Tasks',
        states={
            'readonly': Eval('state') != 'draft',
            },
        domain=[
            ('parent', '=', Eval('shipment_work_project')),
            ('type', '=', 'task'),
            ],
        depends=['state', 'shipment_work_project'])
    warehouse = fields.Many2One('stock.location', 'Warehouse',
        domain=[
            ('type', '=', 'warehouse'),
            ],
        states={
            'required': (Eval('state').in_(['done', 'checked']) &
                Bool(Eval('tasks', []))),
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
            ], 'State', readonly=True, select=True)
    planned_duration = fields.TimeDelta('Planned duration',
        'company_work_time',
        states={
            'readonly': Eval('state').in_(['done', 'checked', 'cancel']),
        },
        depends=['state'])
    total_hours = fields.Function(fields.TimeDelta('Total Hours',
        'company_work_time'),
        'get_total_hours')
    project_invoice_method = fields.Selection(INVOICE_METHODS, 'Invoice Method',
        states={
            'readonly': Eval('state').in_(['checked', 'cancel']),
        }, required=True)
    customer_location = fields.Function(fields.Many2One('stock.location',
            'Customer Location'), 'on_change_with_customer_location')
    warehouse_output = fields.Function(fields.Many2One('stock.location',
            'Warehouse Output'), 'on_change_with_warehouse_output')
    stock_moves = fields.One2Many('stock.move', 'shipment_work',
        'Stock Moves',
        domain=[
            ('from_location', '=', Eval('warehouse_output')),
            ('to_location', '=', Eval('customer_location')),
            ('company', '=', Eval('company')),
            ],
        add_remove=[
            ('state', '=', 'draft'),
            ('shipment_work', '=', None),
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
                ('checked', 'done'),
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
                    'readonly': ~Eval('tasks', []),
                    'icon': 'tryton-ok',
                    },
                'plan': {
                    'invisible': Eval('state') != 'pending',
                    'icon': 'tryton-go-next',
                    },
                'done': {
                    'invisible': ~Eval('state').in_(['planned', 'checked']),
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
                'add_timesheet': {
                    'invisible': Eval('state') != 'done',
                    },
                })

    @classmethod
    def __register__(cls, module_name):
        TableHandler = backend.get('TableHandler')
        cursor = Transaction().connection.cursor()
        table = TableHandler(cls, module_name)
        sql_table = cls.__table__()

        super(ShipmentWork, cls).__register__(module_name)

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

        # Migraton from 4.0: 
        table.not_null_action('sequence', action='remove')
        table.not_null_action('invoice_method', action='remove')
        table.not_null_action('timesheet_invoice_method', action='remove')

    @staticmethod
    def default_state():
        return 'draft'

    @staticmethod
    def default_project_invoice_method():
        return 'manual'

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

    def get_rec_name(self, name):
        return (self.number or str(self.id)
            + ' - ' + self.party.rec_name)

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
        payment_term = None
        if self.party:
            if self.party.customer_payment_term:
                payment_term = self.party.customer_payment_term
        if payment_term:
            self.payment_term = payment_term
            self.payment_term.rec_name = payment_term.rec_name
        else:
            self.payment_term = self.default_payment_term()

    @classmethod
    def get_total_hours(cls, works, name):
        res = {}
        for w in works:
            if w.project:
                res[w.id] = w.project.timesheet_duration
        return res

    @classmethod
    def get_timesheet_work(cls, values):
        TimesheetWork =  Pool().get('timesheet.work')

        work = TimesheetWork()
        work.name = values['number']
        return work

    @classmethod
    def get_project_work(cls, values, type_='project'):
        ProjectWork =  Pool().get('project.work')

        pwork = ProjectWork()
        pwork.name = values['number']
        pwork.parent = values['project']
        pwork.type = type_
        pwork.project_invoice_method = values['project_invoice_method']
        pwork.invoice_product_type = 'service'
        pwork.party = values['party']

        work = cls.get_timesheet_work(values)
        work.save()
        pwork.work = work.id
        return pwork

    @classmethod
    def create(cls, vlist):
        pool = Pool()
        Config = pool.get('stock.configuration')
        Sequence = pool.get('ir.sequence')

        config = Config(1)
        vlist = [x.copy() for x in vlist]

        for values in vlist:
            if not values.get('number'):
                if not config.shipment_work_sequence:
                    cls.raise_user_error('missing_shipment_sequence')
                values['number'] = Sequence.get_id(config.shipment_work_sequence.id)
            # create shipment project work + timesheet work
            work = cls.get_project_work(values)
            work.save()
            values['shipment_work_project'] = work.id

        return super(ShipmentWork, cls).create(vlist)

    @classmethod
    def copy(cls, shipments, defaults=None):
        if defaults is None:
            defaults = {}
        defaults.setdefault('number', None)
        defaults.setdefault('shipment_project_work', None)
        defaults.setdefault('stock_moves', [])
        defaults.setdefault('done_description')
        new_shipments = super(ShipmentWork, cls).copy(shipments, defaults)
        return new_shipments

    @classmethod
    def delete(cls, shipments):
        pool = Pool()
        ProjectWork = pool.get('project.work')
        Work = pool.get('timesheet.work')

        cls.cancel(shipments)
        for shipment in shipments:
            if shipment.state != 'cancel':
                cls.raise_user_error('delete_cancel', (shipment.rec_name,))

        # delete shipment project work + timesheet work
        project_works = [s.shipment_work_project for s in shipments
                if s.shipment_work_project]
        works = [s.shipment_work_project.work for s in shipments
                if s.shipment_work_project and s.shipment_work_project.work]

        super(ShipmentWork, cls).delete(shipments)
        ProjectWork.delete(project_works)
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
        ShipmentOut = Pool().get('stock.shipment.out')

        shipments_to_create = []
        for shipment in shipments:
            stock_shipment = shipment.get_stock_shipment()
            if stock_shipment:
                shipments_to_create.append(stock_shipment._save_values)
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

    @classmethod
    @ModelView.button_action('shipment_work.wizard_timesheet')
    def add_timesheet(cls, shipments):
        pass

    def get_stock_shipment(self):
        pool = Pool()
        ShipmentOut = pool.get('stock.shipment.out')
        moves = [m for m in self.stock_moves if m.state != 'done']
        if not moves:
            return
        shipment = ShipmentOut()
        shipment.company = self.company
        shipment.warehouse = self.warehouse
        shipment.customer = self.party
        shipment.planned_date = self.planned_date
        shipment.effective_date = self.done_date
        shipment.delivery_address = self.party.address_get(type='delivery')
        shipment.reference = self.number
        shipment.moves = moves
        shipment.state = 'draft'
        return shipment


class ShipmentWorkTimesheetAsk(ModelView):
    'Shipment Work Timesheet'
    __name__ = 'shipment_work.shipment.work.timesheet.ask'
    duration = fields.TimeDelta('Duration', 'company_work_time', required=True)
    description = fields.Char('Description')


class ShipmentWorkTimesheet(Wizard):
    'Shipment Work Timesheet'
    __name__ = 'shipment_work.shipment.work.timesheet'
    start_state = 'ask'
    ask = StateView('shipment_work.shipment.work.timesheet.ask',
        'shipment_work.wizard_timesheet_ask_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Ok', 'handle', 'tryton-ok', default=True),
            ])
    handle = StateTransition()

    @classmethod
    def __setup__(cls):
        super(ShipmentWorkTimesheet, cls).__setup__()
        cls._error_messages.update({
            'no_employee': 'You must select an employee in yours user '
                'preferences!',
            'no_project_work': 'You must select a Shipment Project Work before '
                'add timesheet.',
            'no_work': 'You must select a timesheet work in Shipment Project Work '
                'before add timesheet.',
        })

    def transition_handle(self):
        pool = Pool()
        ShipmentWork = pool.get('shipment.work')
        Line = pool.get('timesheet.line')
        User = pool.get('res.user')
        Date = pool.get('ir.date')

        user = User(Transaction().user)
        if not user.employee:
            self.raise_user_error('no_employee')

        swork = ShipmentWork(Transaction().context['active_id'])
        if not swork.shipment_work_project:
            self.raise_user_error('no_project_work')
        if not swork.shipment_work_project.work:
            self.raise_user_error('no_work')

        line = Line()
        line.employee = user.employee
        line.date = Date.today()
        line.duration = self.ask.duration
        line.work = swork.shipment_work_project.work
        line.description = self.ask.description
        line.save()

        return 'end'


class ShipmentWorkOpenTimesheetLine(Wizard):
    'Shipment Work Open Timeshee tLine'
    __name__ = 'shipemnt.work.open.timesheet.line'
    start_state = 'open_'
    open_ = StateAction('timesheet.act_line_form')

    def do_open_(self, action):
        ShipmentWork = Pool().get('shipment.work')

        active_ids = Transaction().context['active_ids']
        sworks = ShipmentWork.search([('id', 'in', active_ids)])
        works = [s.shipment_work_project for s in sworks
                if s.shipment_work_project]

        action['pyson_domain'] = PYSONEncoder().encode([
                ('work', 'in', [w.work.id for w in works if w.work]),
                ])

        return action, {}


class ProjectWork:
    __metaclass__ = PoolMeta
    __name__ = 'project.work'
    shipment_work = fields.Many2One('shipment.work', 'Shipment Work')


class TimesheetLine:
    __name__ = 'timesheet.line'
    __metaclass__ = PoolMeta

    @classmethod
    def __register__(cls, module_name):
        TableHandler = backend.get('TableHandler')
        table = TableHandler(cls, module_name)

        # Migration from 4.0:
        table.not_null_action('invoice_method', action='remove')

        super(TimesheetLine, cls).__register__(module_name)


class StockMove:
    __name__ = 'stock.move'
    __metaclass__ = PoolMeta
    shipment_work = fields.Many2One('shipment.work', 'Shipment Work')

    @classmethod
    def __register__(cls, module_name):
        TableHandler = backend.get('TableHandler')
        table = TableHandler(cls, module_name)

        # Migration from 4.0: rename work_shipment into shipment_work
        if (table.column_exist('work_shipment')
                and not table.column_exist('number')):
            table.column_rename('work_shipment', 'shipment_work')

        super(StockMove, cls).__register__(module_name)
