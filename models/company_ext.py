from odoo import models, fields


class ResCompanyVidriosExt(models.Model):
    _inherit = 'res.company'

    vidrios_pos_config_id = fields.Many2one(
        'pos.config',
        string='POS para pagos de taller',
    )
    vidrios_pos_product_id = fields.Many2one(
        'product.product',
        string='Producto de pago taller (POS)',
        domain=[('available_in_pos', '=', True)],
    )
