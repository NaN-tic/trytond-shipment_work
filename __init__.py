# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .configuration import *
from .shipment import *

def register():
    Pool.register(
        Configuration,
        ConfigurationCompany,
        ShipmentWork,
        ShipmentWorkEmployee,
        ShipmentWorkTimesheetAsk,
        ProjectWork,
        TimesheetLine,
        StockMove,
        module='shipment_work', type_='model')
    Pool.register(
        ShipmentWorkTimesheet,
        ShipmentWorkOpenTimesheetLine,
        module='shipment_work', type_='wizard')
