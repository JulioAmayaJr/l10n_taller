from odoo import models, fields, api


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
    depth = fields.Float('Profundidad (cm)', digits=(10, 2))

    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        related='order_id.currency_id', store=True, readonly=True
    )

    area = fields.Float(
        'Área (m²)', compute='_compute_area', store=True, digits=(10, 4)
    )
    price_unit = fields.Monetary(
        'Precio unitario', compute='_compute_price', store=True,
        currency_field='currency_id'
    )
    price_subtotal = fields.Monetary(
        'Subtotal', compute='_compute_price', store=True,
        currency_field='currency_id'
    )

    characteristic_value_ids = fields.One2many(
        'vidrios.order.line.characteristic', 'line_id', string='Características'
    )
    notes = fields.Char('Notas')

    @api.depends('width', 'height')
    def _compute_area(self):
        for line in self:
            line.area = (line.width / 100.0) * (line.height / 100.0)

    @api.depends('area', 'product_id.price_m2', 'product_id.min_price', 'quantity')
    def _compute_price(self):
        for line in self:
            if line.product_id:
                base = line.area * line.product_id.price_m2
                price_unit = max(base, line.product_id.min_price)
            else:
                price_unit = 0.0
            line.price_unit = price_unit
            line.price_subtotal = price_unit * line.quantity

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if not self.product_id:
            return
        self.characteristic_value_ids = [(5, 0, 0)]
        new_vals = []
        for char in self.product_id.characteristic_ids.sorted('sequence'):
            new_vals.append((0, 0, {
                'characteristic_id': char.id,
                'value_char': '',
                'value_boolean': False,
                'value_selection': '',
            }))
        self.characteristic_value_ids = new_vals

    def get_cutlist(self):
        """
        Genera lista de corte aplicando fórmulas del producto a las medidas.
        Claves por entrada: name, material_type, quantity, size, unit, notes.
        Solo glass agrega: cut_width, cut_height (medidas de corte en cm).
        """
        self.ensure_one()
        result = []
        material_labels = dict(
            self.env['vidrios.formula']._fields['material_type'].selection
        )
        for formula in self.product_id.formula_ids.sorted('sequence'):
            cut = formula.compute_cut_result(self.width, self.height)
            entry = {
                'name': formula.name,
                'material_type': material_labels.get(formula.material_type, formula.material_type),
                'quantity': formula.quantity * self.quantity,
                'size': cut['size'],
                'unit': cut['unit'],
                'cut_width': cut.get('cut_width'),
                'cut_height': cut.get('cut_height'),
                'notes': formula.notes or '',
            }
            result.append(entry)
        return result

    def get_assembly_list(self):
        """
        Lista de materiales para la Hoja de Ensamble.
        Mismo formato que el rollo: cm para perfiles/vidrio, m para lineales.
          - glass  : "94.9 cm" / "188.7 cm"  en width_str / height_str
          - profile: "100.0 cm"               en length_str
          - linear : "4.0 m"                  en length_str
          - hardware: unit='uds', sin medidas
        """
        self.ensure_one()
        result = []
        for formula in self.product_id.formula_ids.sorted('sequence'):
            cut = formula.compute_cut_result(self.width, self.height)
            entry = {
                'code': formula.material_code or '',
                'name': formula.name,
                'material_type': formula.material_type,
                'unit': cut['unit'],
                'qty_each': formula.quantity,
                'qty_total': formula.quantity * self.quantity,
                'width_str': '',
                'height_str': '',
                'length_str': '',
                'notes': formula.notes or '',
            }
            if formula.material_type == 'glass' and cut.get('cut_width') is not None:
                entry['width_str'] = '%.1f cm' % cut['cut_width']
                entry['height_str'] = '%.1f cm' % cut['cut_height']
            elif formula.material_type == 'profile' and cut['size'] is not None:
                entry['length_str'] = '%.1f cm' % cut['size']
            elif formula.material_type == 'linear' and cut['size'] is not None:
                # Mismo formato que el rollo: hasta 3 sig. decimales sin ceros finales
                entry['length_str'] = ('%g m' % round(cut['size'], 3))
            result.append(entry)
        return result

    def get_cutlist_summary(self):
        """
        Resumen de materiales agrupados por tipo para estimados/inventario.
        Retorna lista de {material_type, name, total, unit}.
        """
        self.ensure_one()
        summary = {}
        for formula in self.product_id.formula_ids:
            cut = formula.compute_cut_result(self.width, self.height)
            key = (formula.material_type, formula.name)
            qty = formula.quantity * self.quantity
            if formula.material_type == 'linear' and cut['size'] is not None:
                total = round(cut['size'] * qty, 3)
            elif formula.material_type == 'hardware':
                total = qty
            else:
                total = None
            if total is not None:
                if key not in summary:
                    summary[key] = {'name': formula.name, 'total': 0.0, 'unit': cut['unit']}
                summary[key]['total'] += total
        return list(summary.values())
