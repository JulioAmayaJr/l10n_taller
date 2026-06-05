from odoo import models, fields, api


class VidriosOrderLineCharacteristic(models.Model):
    _name = 'vidrios.order.line.characteristic'
    _description = 'Valor de Característica en Línea de Orden'
    _order = 'characteristic_id'

    line_id = fields.Many2one(
        'vidrios.order.line', string='Línea', required=True, ondelete='cascade'
    )
    characteristic_id = fields.Many2one(
        'vidrios.characteristic', string='Característica', required=True, ondelete='restrict'
    )
    field_type = fields.Selection(
        related='characteristic_id.field_type', string='Tipo', readonly=True, store=True
    )
    char_name = fields.Char(
        related='characteristic_id.name', string='Nombre', readonly=True
    )
    selection_values = fields.Char(
        related='characteristic_id.selection_values', readonly=True
    )
    visible_on_ticket = fields.Boolean(
        related='characteristic_id.visible_on_ticket', readonly=True, store=True
    )

    value_char = fields.Char('Valor texto')
    value_boolean = fields.Boolean('Valor sí/no')
    value_selection = fields.Char('Valor selección')

    def get_display_value(self):
        self.ensure_one()
        if self.field_type == 'char':
            return self.value_char or ''
        if self.field_type == 'boolean':
            return 'Sí' if self.value_boolean else 'No'
        if self.field_type == 'select':
            return self.value_selection or ''
        return ''

    def get_ticket_label(self):
        self.ensure_one()
        return self.characteristic_id.get_ticket_label()
