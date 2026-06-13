from odoo import models, fields, api, _
from odoo.exceptions import UserError


class VidriosOrderLine(models.Model):
    _name = 'vidrios.order.line'
    _description = 'Línea de Orden de Taller'
    _order = 'order_id, sequence'

    order_id = fields.Many2one(
        'vidrios.order', string='Orden', required=True, ondelete='cascade'
    )
    sequence = fields.Integer('Sec.', default=10)
    product_id = fields.Many2one('vidrios.product', string='Producto', required=True)
    quantity = fields.Integer('Cantidad', default=1)
    width = fields.Float('Ancho (cm)', digits=(10, 2))
    height = fields.Float('Alto (cm)', digits=(10, 2))
    depth = fields.Float('Largo (cm)', digits=(10, 2))

    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        related='order_id.currency_id', store=True, readonly=True
    )

    area = fields.Float(
        'Área (m²)', compute='_compute_area', store=True, digits=(10, 4)
    )
    # price_manual=True bloquea el recompute automático; el usuario fijó el precio a mano.
    price_manual = fields.Boolean('Precio manual', default=False)
    price_unit = fields.Monetary(
        'Precio unitario', compute='_compute_price_unit', store=True, readonly=False,
        currency_field='currency_id'
    )
    price_subtotal = fields.Monetary(
        'Subtotal', compute='_compute_subtotal', store=True,
        currency_field='currency_id'
    )

    product_requires_depth = fields.Boolean(
        related='product_id.requires_depth', readonly=True
    )
    characteristic_value_ids = fields.One2many(
        'vidrios.order.line.characteristic', 'line_id', string='Características'
    )
    notes = fields.Char('Notas')

    # Resumen rápido de características visibles en ticket, para la columna de la lista
    char_summary = fields.Char(
        'Resumen características',   # distinto de 'Características' de characteristic_value_ids
        compute='_compute_char_summary',
    )

    @api.depends(
        'characteristic_value_ids.visible_on_ticket',
        'characteristic_value_ids.value_char',
        'characteristic_value_ids.value_boolean',
        'characteristic_value_ids.value_option_id',
        'characteristic_value_ids.value_selection',
    )
    def _compute_char_summary(self):
        for line in self:
            parts = []
            for cv in line.characteristic_value_ids.filtered('visible_on_ticket'):
                val = cv.get_display_value()
                if val:
                    parts.append(val)
            line.char_summary = ' | '.join(parts) if parts else ''

    @api.depends('width', 'height')
    def _compute_area(self):
        for line in self:
            line.area = (line.width / 100.0) * (line.height / 100.0)

    @api.depends('area', 'product_id.price_m2', 'product_id.min_price', 'price_manual')
    def _compute_price_unit(self):
        for line in self:
            if line.price_manual:
                continue  # precio fijado manualmente: conserva el valor almacenado
            if line.product_id:
                base = line.area * line.product_id.price_m2
                line.price_unit = max(base, line.product_id.min_price)
            else:
                line.price_unit = 0.0

    @api.depends('price_unit', 'quantity')
    def _compute_subtotal(self):
        for line in self:
            line.price_subtotal = (line.price_unit or 0.0) * line.quantity

    def _formula_price(self):
        """Precio que devolvería la fórmula (sin override manual)."""
        self.ensure_one()
        if not self.product_id:
            return 0.0
        base = self.area * self.product_id.price_m2
        return max(base, self.product_id.min_price)

    @api.onchange('price_unit')
    def _onchange_price_unit(self):
        """Marca price_manual=True solo cuando el usuario cambia el precio respecto a la fórmula."""
        if self.price_unit != self._formula_price():
            self.price_manual = True

    def action_reset_price(self):
        """Restaura el precio de fórmula: borra el override manual y recalcula."""
        self.ensure_one()
        self.price_manual = False
        self._compute_price_unit()
        self._compute_subtotal()

    def action_duplicate_line(self):
        """Duplica la línea (botón ícono en la lista). Cierra el dialog y refresca la lista."""
        self.ensure_one()
        if not self.order_id or not (isinstance(self.id, int) and self.id > 0):
            raise UserError(_('Guarda la orden antes de duplicar la línea.'))
        self.copy(default={'order_id': self.order_id.id})
        self.order_id._recompute_materials()
        return True

    def action_save_and_duplicate(self):
        """
        Botón 'Guardar y duplicar' del footer del dialog.
        Odoo guarda la línea actual antes de llamar al método (type=object),
        así self ya tiene id real y order_id persistido.
        Crea una copia exacta y abre esa copia en un nuevo dialog.
        """
        self.ensure_one()
        if not self.order_id or not self.order_id.id:
            raise UserError(_('Guarda la orden antes de duplicar la línea.'))
        new_line = self.copy(default={'order_id': self.order_id.id})
        self.order_id._recompute_materials()
        view = self.env.ref('vidrios_castillo_taller.view_vidrios_order_line_form')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'vidrios.order.line',
            'res_id': new_line.id,
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
        }

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if not self.product_id:
            self.characteristic_value_ids = [(5, 0, 0)]
            return

        # self._origin.product_id es el valor GUARDADO en BD (False para nuevas líneas).
        # Si el producto no cambió respecto al guardado, solo completamos las que falten
        # y NUNCA borramos: esto evita que Odoo, al re-invocar el onchange durante el
        # guardado/Cotizar, limpie los valores ya capturados.
        origin_product_id = self._origin.product_id.id if self._origin else False
        product_changed = (origin_product_id != self.product_id.id)

        existing_char_ids = {
            cv.characteristic_id.id
            for cv in self.characteristic_value_ids
            if cv.characteristic_id
        }

        if product_changed and not existing_char_ids:
            # Línea nueva (sin características aún): generar todas
            self.characteristic_value_ids = [
                (0, 0, {
                    'characteristic_id': char.id,
                    'value_char': '',
                    'value_boolean': False,
                    'value_option_id': False,
                })
                for char in self.product_id.characteristic_ids.sorted('sequence')
            ]
        elif product_changed:
            # Producto distinto y ya había características: revisar si son del nuevo producto
            product_char_ids = {char.id for char in self.product_id.characteristic_ids}
            stale = existing_char_ids - product_char_ids
            if stale:
                # Las existentes son del producto anterior → limpiar y regenerar
                self.characteristic_value_ids = [(5, 0, 0)] + [
                    (0, 0, {
                        'characteristic_id': char.id,
                        'value_char': '',
                        'value_boolean': False,
                        'value_option_id': False,
                    })
                    for char in self.product_id.characteristic_ids.sorted('sequence')
                ]
            else:
                # Producto "cambió" pero las características coinciden (raro): solo agregar faltantes
                self._add_missing_characteristics(existing_char_ids)
        else:
            # Mismo producto (re-apertura de popup, recompute durante Cotizar, etc.)
            # SOLO agregar las que falten. Nunca borrar.
            self._add_missing_characteristics(existing_char_ids)

    def _add_missing_characteristics(self, existing_char_ids):
        new_rows = [
            (0, 0, {
                'characteristic_id': char.id,
                'value_char': '',
                'value_boolean': False,
                'value_option_id': False,
            })
            for char in self.product_id.characteristic_ids.sorted('sequence')
            if char.id not in existing_char_ids
        ]
        if new_rows:
            self.characteristic_value_ids = new_rows

    def get_cutlist(self):
        """
        Genera lista de corte aplicando fórmulas del producto a las medidas.
        Claves: name, code, material_type, quantity, size, unit, notes.
        Vidrio agrega: cut_width/cut_height (alias), cut_a/cut_b, dim_a_label/dim_b_label, panel_str.
        """
        self.ensure_one()
        result = []
        material_labels = dict(
            self.env['vidrios.formula']._fields['material_type'].selection
        )
        for formula in self.product_id.formula_ids.sorted('sequence'):
            cut = formula.compute_cut_result(self.width, self.height, self.depth)
            cut_a = cut.get('cut_a')
            cut_b = cut.get('cut_b')
            entry = {
                'name': formula.material_product_id.display_name or '',
                'code': formula.material_product_id.default_code or '',
                'material_type': material_labels.get(formula.material_type, formula.material_type),
                'quantity': formula.quantity * self.quantity,
                'size': cut['size'],
                'unit': cut['unit'],
                'cut_width': cut.get('cut_width'),
                'cut_height': cut.get('cut_height'),
                'cut_a': cut_a,
                'cut_b': cut_b,
                'dim_a_label': cut.get('dim_a_label', ''),
                'dim_b_label': cut.get('dim_b_label', ''),
                'panel_str': ('%.1f × %.1f cm' % (cut_a, cut_b)) if cut_a is not None else '',
                'notes': formula.notes or '',
            }
            result.append(entry)
        return result

    def get_assembly_list(self):
        """
        Lista de materiales para la Hoja de Ensamble.
          - glass  : width_str/height_str (alias dim_a/dim_b), dim_a_label/dim_b_label, panel_str
          - profile: length_str
          - linear : length_str
          - hardware: unit='uds', sin medidas
        """
        self.ensure_one()
        result = []
        for formula in self.product_id.formula_ids.sorted('sequence'):
            cut = formula.compute_cut_result(self.width, self.height, self.depth)
            cut_a = cut.get('cut_a')
            cut_b = cut.get('cut_b')
            entry = {
                'code': formula.material_product_id.default_code or '',
                'name': formula.material_product_id.display_name or '',
                'material_type': formula.material_type,
                'unit': cut['unit'],
                'qty_each': formula.quantity,
                'qty_total': formula.quantity * self.quantity,
                'width_str': '',
                'height_str': '',
                'length_str': '',
                'dim_a_label': cut.get('dim_a_label', 'Ancho'),
                'dim_b_label': cut.get('dim_b_label', 'Alto'),
                'panel_str': ('%.1f × %.1f cm' % (cut_a, cut_b)) if cut_a is not None else '',
                'notes': formula.notes or '',
            }
            if formula.material_type == 'glass' and cut_a is not None:
                entry['width_str'] = '%.1f cm' % cut_a
                entry['height_str'] = '%.1f cm' % cut_b
            elif formula.material_type == 'profile' and cut['size'] is not None:
                entry['length_str'] = '%.1f cm' % cut['size']
            elif formula.material_type == 'linear' and cut['size'] is not None:
                entry['length_str'] = ('%g m' % round(cut['size'], 3))
            result.append(entry)
        return result

    # ------------------------------------------------------------------ #
    # Triggers para recálculo de materiales estimados                     #
    # ------------------------------------------------------------------ #

    _MATERIAL_TRIGGER_FIELDS = {'width', 'height', 'depth', 'quantity', 'product_id'}

    def write(self, vals):
        res = super().write(vals)
        if self._MATERIAL_TRIGGER_FIELDS & set(vals):
            self.mapped('order_id')._recompute_materials()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.mapped('order_id')._recompute_materials()
        return lines

    def unlink(self):
        orders = self.mapped('order_id')
        res = super().unlink()
        orders._recompute_materials()
        return res

    def get_cutlist_summary(self):
        """
        Resumen de materiales agrupados por producto de inventario.
        Retorna lista de {material_type, name, code, total, unit}.
        El mismo producto puede aparecer en múltiples fórmulas; sus totales se suman.
        """
        self.ensure_one()
        summary = {}
        for formula in self.product_id.formula_ids:
            cut = formula.compute_cut_result(self.width, self.height, self.depth)
            # Clave: (tipo, id de producto) para agregar mismo material de distintas fórmulas
            pid = formula.material_product_id.id or 0
            key = (formula.material_type, pid, formula.id if not pid else 0)
            qty = formula.quantity * self.quantity
            if formula.material_type == 'linear' and cut['size'] is not None:
                total = round(cut['size'] * qty, 3)
            elif formula.material_type == 'hardware':
                total = qty
            else:
                total = None
            if total is not None:
                if key not in summary:
                    summary[key] = {
                        'name': formula.material_product_id.display_name or '',
                        'code': formula.material_product_id.default_code or '',
                        'total': 0.0,
                        'unit': cut['unit'],
                    }
                summary[key]['total'] += total
        return list(summary.values())
