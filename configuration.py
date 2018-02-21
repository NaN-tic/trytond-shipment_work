# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.modules.company.model import CompanyValueMixin

__all__ = ['Configuration', 'ConfigurationCompany']


class Configuration:
    __name__ = 'stock.configuration'
    __metaclass__ = PoolMeta
    shipment_work_sequence = fields.MultiValue(fields.Many2One(
            'ir.sequence', 'Shipment Work Sequence',
            domain=[
                ('company', 'in',
                    [Eval('context', {}).get('company', -1), None]),
                ('code', '=', 'shipment.work'),
                ], required=True))
    shipment_work_hours_product = fields.MultiValue(fields.Many2One(
            'product.product', 'Shipment Work Hours Product',
            domain=[
                ('type', '=', 'service'),
                ('salable', '=', True),
                ],
            required=True,
            help='The product used to invoice '
            'the service hours of a shipment'))
    shipment_work_journal = fields.MultiValue(
        fields.Many2One(
            'account.journal', 'Shipment Work Journal', required=True))

    @classmethod
    def multivalue_model(cls, field):
        pool = Pool()
        if field in {
                'shipment_work_sequence',
                'shipment_work_hours_product',
                'shipment_work_journal'}:
            return pool.get('stock.configuration.company')
        return super(Configuration, cls).multivalue_model(field)


class ConfigurationCompany(ModelSQL, CompanyValueMixin):
    'Stock Configuration per Company'
    __name__ = 'stock.configuration.company'

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
    shipment_work_journal = fields.Many2One('account.journal',
        'Shipment Work Journal')
