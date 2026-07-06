from odoo import models, fields


class PosOrderExt(models.Model):
    _inherit = 'pos.order'

    vidrios_order_id = fields.Many2one(
        'vidrios.order',
        string='Orden de Taller',
        index=True,
        ondelete='set null',
    )
