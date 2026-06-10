from odoo import models, fields, api


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
    option_ids = fields.One2many(
        'vidrios.characteristic.option', 'characteristic_id', string='Opciones'
    )

    @api.model
    def sync_all_options(self):
        """Sync option_ids for every select characteristic. Called by data file on install/update."""
        self.search([('field_type', '=', 'select')])._sync_options()

    def get_ticket_label(self):
        self.ensure_one()
        return self.ticket_label or self.name

    def get_selection_list(self):
        self.ensure_one()
        if self.selection_values:
            return [v.strip() for v in self.selection_values.split(',') if v.strip()]
        return []

    # ------------------------------------------------------------------ #
    # Sync option_ids from selection_values                               #
    # ------------------------------------------------------------------ #

    def _sync_options(self):
        """
        Mantiene option_ids sincronizados con selection_values.
        NUNCA borra opciones existentes para no romper value_option_id en
        líneas de orden guardadas.  Solo crea/actualiza.
        """
        Option = self.env['vidrios.characteristic.option']
        for char in self:
            if char.field_type != 'select' or not char.selection_values:
                # Para no-select no tocamos las opciones (no las borramos)
                continue
            new_names = [v.strip() for v in char.selection_values.split(',') if v.strip()]
            existing = {opt.name: opt for opt in char.option_ids}
            for i, name in enumerate(new_names):
                if name not in existing:
                    Option.create({
                        'characteristic_id': char.id,
                        'name': name,
                        'sequence': (i + 1) * 10,
                    })
                else:
                    existing[name].write({'sequence': (i + 1) * 10})
            # Opciones obsoletas → NO se borran; podrían estar referenciadas en
            # value_option_id de líneas de orden. Se dejan con secuencia alta para
            # que no molesten en el desplegable.

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_options()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'selection_values' in vals or 'field_type' in vals:
            self._sync_options()
        return res
