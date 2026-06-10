from odoo import models, fields, api


class VidriosOrderMaterial(models.Model):
    _name = 'vidrios.order.material'
    _description = 'Material estimado por Orden de Taller'
    _order = 'order_id, id'

    order_id = fields.Many2one(
        'vidrios.order', string='Orden', required=True,
        ondelete='cascade', index=True,
    )
    product_id = fields.Many2one(
        'product.product', string='Material', required=True,
    )
    qty_needed = fields.Float('Necesario', digits=(10, 4))
    uom_name = fields.Char('Unidad')

    # Calculados en tiempo real contra stock.quant (no almacenados)
    qty_available = fields.Float(
        'Disponible',
        compute='_compute_availability',
        digits=(10, 4),
    )
    shortage = fields.Boolean(
        'Falta stock',
        compute='_compute_availability',
    )

    @api.depends('product_id', 'qty_needed')
    def _compute_availability(self):
        for rec in self:
            avail = rec.product_id.qty_available if rec.product_id else 0.0
            rec.qty_available = avail
            rec.shortage = avail < rec.qty_needed - 0.0001
