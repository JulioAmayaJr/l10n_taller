from odoo import models, fields


class VidrosPriceTier(models.Model):
    _name = 'vidrios.price.tier'
    _description = 'Rango de Precio por Área'
    _order = 'product_id, min_area'

    product_id = fields.Many2one(
        'vidrios.product', string='Producto', required=True, ondelete='cascade', index=True
    )
    min_area = fields.Float('Desde m²', digits=(10, 4), default=0.0)
    price_mode = fields.Selection([
        ('fixed', 'Fijo'),
        ('per_m2', 'Por m²'),
    ], string='Modo', required=True, default='fixed')
    amount = fields.Float('Precio', digits=(10, 2))
