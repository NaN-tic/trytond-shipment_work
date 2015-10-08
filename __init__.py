# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .configuration import *
from .shipment import *
from .invoice import *


def register():
    Pool.register(
        Configuration,
        ConfigurationCompany,
        ShipmentWork,
        ShipmentWorkProduct,
        ShipmentWorkWorkRelation,
        ShipmentWorkEmployee,
        TimesheetLine,
        Sale,
        SaleLine,
        StockMove,
        InvoiceLine,
        module='shipment_work', type_='model')
