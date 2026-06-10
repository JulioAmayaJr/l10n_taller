from odoo import models, fields


class VidriosCharacteristicOption(models.Model):
    _name = 'vidrios.characteristic.option'
    _description = 'Opción de Característica de Producto'
    _order = 'characteristic_id, sequence, name'
    _rec_name = 'name'

    characteristic_id = fields.Many2one(
        'vidrios.characteristic',
        string='Característica',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char('Opción', required=True)
    sequence = fields.Integer('Secuencia', default=10)
