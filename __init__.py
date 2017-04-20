# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import configuration
from . import invoice
from . import shipment


def register():
    Pool.register(
        configuration.Configuration,
        configuration.ConfigurationCompany,
        invoice.InvoiceLine,
        shipment.ShipmentWork,
        shipment.ShipmentWorkWorkRelation,
        shipment.ShipmentWorkProduct,
        shipment.ShipmentWorkEmployee,
        shipment.StockMove,
        shipment.TimesheetLine,
        module='shipment_work', type_='model')
