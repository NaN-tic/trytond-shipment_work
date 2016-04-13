# -*- encoding: utf-8 -*-
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta
from trytond.pyson import Eval

__all__ = ['InvoiceLine']


class InvoiceLine:
    __name__ = 'account.invoice.line'
    __metaclass__ = PoolMeta

    shipment_work = fields.Many2One('shipment.work', 'Shipment Work',
        states={
            'invisible': ~Eval('_parent_invoice', {}).get('type',
                Eval('invoice_type')).in_(['in_invoice', 'in_credit_note']),
            },
        depends=[])
