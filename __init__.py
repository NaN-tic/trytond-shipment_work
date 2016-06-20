# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .configuration import *
from .invoice import *
from .shipment import *

def register():
    Pool.register(
        Configuration,
        ConfigurationCompany,
        InvoiceLine,
        ShipmentWork,
        ShipmentWorkProduct,
        ShipmentWorkWorkRelation,
        ShipmentWorkEmployee,
        StockMove,
        TimesheetLine,
        module='shipment_work', type_='model')
