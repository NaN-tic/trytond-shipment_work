# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .shipment import *


def register():
    Pool.register(
        Configuration,
        ConfigurationCompany,
        ShipmentWork,
        ShipmentWorkProduct,
        ShipmentWorkWorkRelation,
        ShipmentWorkEmployee,
        TimesheetLine,
        SaleLine,
        StockMove,
        module='shipment_work', type_='model')
