from odoo import models, fields


class VidriosCharacteristic(models.Model):
    _name = 'vidrios.characteristic'
    _description = 'Característica de Producto'
    _order = 'product_id, sequence, name'

    product_id = fields.Many2one(
        'vidrios.product', string='Producto', required=True, ondelete='cascade'
    )
    name = fields.Char('Nombre', required=True)
    sequence = fields.Integer('Secuencia', default=10)
    field_type = fields.Selection(
        [('char', 'Texto'), ('select', 'Selección'), ('boolean', 'Sí/No')],
        string='Tipo de campo', required=True, default='char'
    )
    selection_values = fields.Char(
        'Opciones (separadas por coma)',
        help='Solo si Tipo = Selección. Ej: Bronce,Natural,Blanco'
    )
    visible_on_ticket = fields.Boolean('Visible en ticket cliente', default=False)
    ticket_label = fields.Char(
        'Etiqueta en ticket',
        help='Texto a mostrar en el ticket del cliente (si está vacío usa el Nombre)'
    )

    def get_ticket_label(self):
        self.ensure_one()
        return self.ticket_label or self.name

    def get_selection_list(self):
        self.ensure_one()
        if self.selection_values:
            return [v.strip() for v in self.selection_values.split(',') if v.strip()]
        return []
