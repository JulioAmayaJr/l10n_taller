from odoo import models, fields


class VidriosExtra(models.Model):
    _name = 'vidrios.extra'
    _description = 'Extra de Orden (Flete, Instalación, etc.)'

    order_id = fields.Many2one(
        'vidrios.order', string='Orden', required=True, ondelete='cascade'
    )
    name = fields.Char('Concepto', required=True)
    price = fields.Float('Precio', digits=(10, 2))
