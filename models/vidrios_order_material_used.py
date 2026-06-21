from odoo import models, fields


class VidriosOrderMaterialUsed(models.Model):
    _name = 'vidrios.order.material.used'
    _description = 'Material realmente usado en Orden de Taller'
    _order = 'order_id, id'

    order_id = fields.Many2one(
        'vidrios.order', string='Orden', required=True,
        ondelete='cascade', index=True,
    )
    product_id = fields.Many2one(
        'product.product', string='Material', required=True,
    )
    qty_used = fields.Float('Cantidad usada', digits=(10, 4))
    uom_name = fields.Char('Unidad')
    notes = fields.Char('Nota')
