from odoo import models, fields


class StockMove(models.Model):
    _inherit = 'stock.move'

    vidrios_order_id = fields.Many2one(
        'vidrios.order',
        string='Orden de Taller',
        index=True,
        ondelete='set null',
    )
