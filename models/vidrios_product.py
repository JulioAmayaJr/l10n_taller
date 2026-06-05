from odoo import models, fields


class VidriosProduct(models.Model):
    _name = 'vidrios.product'
    _description = 'Tipo de Producto Vidrios Castillo'
    _order = 'name'

    name = fields.Char('Nombre', required=True)
    active = fields.Boolean('Activo', default=True)
    price_m2 = fields.Float('Precio por m²', digits=(10, 2), default=0.0)
    min_price = fields.Float('Precio mínimo', digits=(10, 2), default=0.0)
    characteristic_ids = fields.One2many(
        'vidrios.characteristic', 'product_id', string='Características'
    )
    formula_ids = fields.One2many(
        'vidrios.formula', 'product_id', string='Fórmulas de despiece'
    )
