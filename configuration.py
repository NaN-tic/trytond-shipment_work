# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelSQL, Model, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction

__all__ = ['Configuration', 'ConfigurationCompany']


class Configuration:
    __name__ = 'stock.configuration'
    __metaclass__ = PoolMeta

    shipment_work_sequence = fields.Function(fields.Many2One('ir.sequence',
            'Shipment Work Sequence',
            domain=[
                ('company', 'in',
                    [Eval('context', {}).get('company', -1), None]),
                ('code', '=', 'shipment.work'),
                ], required=True),
        'get_company_config', 'set_company_config')

    shipment_work_hours_product = fields.Function(fields.Many2One(
            'product.product', 'Shipment Work Hours Product',
            help='The product used to invoice the service hours of a shipment',
            domain=[
                ('type', '=', 'service'),
                ('salable', '=', True),
                ]),
        'get_company_config', 'set_company_config')

    @classmethod
    def get_company_config(self, configs, names):
        pool = Pool()
        CompanyConfig = pool.get('stock.configuration.company')

        company_id = Transaction().context.get('company')
        company_configs = CompanyConfig.search([
                ('company', '=', company_id),
                ])

        res = {}
        for fname in names:
            res[fname] = {
                configs[0].id: None,
                }
            if company_configs:
                val = getattr(company_configs[0], fname)
                if isinstance(val, Model):
                    val = val.id
                res[fname][configs[0].id] = val
        return res

    @classmethod
    def set_company_config(self, configs, name, value):
        pool = Pool()
        CompanyConfig = pool.get('stock.configuration.company')

        company_id = Transaction().context.get('company')
        company_configs = CompanyConfig.search([
                ('company', '=', company_id),
                ])
        if company_configs:
            company_config = company_configs[0]
        else:
            company_config = CompanyConfig(company=company_id)
        setattr(company_config, name, value)
        company_config.save()


class ConfigurationCompany(ModelSQL):
    'Stock Configuration per Company'
    __name__ = 'stock.configuration.company'

    company = fields.Many2One('company.company', 'Company', required=True,
        ondelete='CASCADE', select=True)
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


