# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.

try:
    from trytond.modules.shipment_work.test_shipment_work import suite
except ImportError:
    from .test_shipment_work import suite

__all__ = ['suite']
