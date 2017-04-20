# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool, PoolMeta

__all__ = ['InvoiceLine']


class InvoiceLine:
    __metaclass__ = PoolMeta
    __name__ = 'account.invoice.line'

    @property
    def origin_name(self):
        ShipmentWork = Pool().get('shipment.work')
        name = super(InvoiceLine, self).origin_name
        if isinstance(self.origin, ShipmentWork):
            name = self.origin.rec_name
        return name

    @classmethod
    def _get_origin(cls):
        models = super(InvoiceLine, cls)._get_origin()
        models.append('shipment.work')
        return models
