from odoo import models, fields, api


MATERIAL_TYPE = [
    ('profile', 'Perfil'),
    ('glass', 'Vidrio'),
    ('hardware', 'Herraje'),
    ('linear', 'Lineal'),
]

UNIT_BY_TYPE = {
    'profile': 'cm',
    'glass': 'm²',
    'hardware': 'uds',
    'linear': 'm',
}

# Incluye 'depth' (Largo) para productos 3D
_DIM_LABEL = {'width': 'Ancho', 'height': 'Alto', 'depth': 'Largo', 'fixed': 'Fija'}

# Selección de dimensión usada en perfil, vidrio y lineal
_DIM_SELECTION = [('width', 'Ancho'), ('height', 'Alto'), ('depth', 'Largo')]


class VidriosFormula(models.Model):
    _name = 'vidrios.formula'
    _description = 'Fórmula de Despiece Paramétrica'
    _rec_name = 'name'
    _order = 'product_id, sequence'

    product_id = fields.Many2one(
        'vidrios.product', string='Producto', required=True, ondelete='cascade'
    )
    sequence = fields.Integer('Secuencia', default=10)

    material_product_id = fields.Many2one(
        'product.product',
        string='Producto de inventario',
        help='Pieza enlazada a inventario. Al producir se descuenta la cantidad calculada.',
        ondelete='set null',
    )

    name = fields.Char(
        'Pieza',
        compute='_compute_name',
        store=True,
        readonly=True,
        copy=False,
    )

    formula_summary = fields.Char(
        'Fórmula',
        compute='_compute_formula_summary',
    )

    material_type = fields.Selection(
        MATERIAL_TYPE, string='Tipo de material', required=True, default='profile'
    )
    quantity = fields.Float('Cantidad', digits=(10, 3), default=1.0)
    notes = fields.Char('Notas')

    # --- Perfil y Lineal: dimensión base ahora incluye Largo (depth) ---
    base_dimension = fields.Selection(
        _DIM_SELECTION + [('fixed', 'Fija')],
        string='Dimensión base', default='width'
    )
    divisor = fields.Float('Divisor', default=1.0)
    addition = fields.Float('Adición (cm)', default=0.0)
    deduction = fields.Float('Deducción (cm)', default=0.0)

    # --- Vidrio: panel de dos dimensiones configurables ---
    # glass_dim_a / glass_dim_b eligen qué dimensión del artículo usa cada eje del panel.
    # Por defecto width×height para compatibilidad con fórmulas 2D existentes.
    glass_dim_a = fields.Selection(
        _DIM_SELECTION,
        string='Dimensión A', default='width',
        help='Dimensión del artículo que corresponde al primer lado del panel de vidrio.',
    )
    glass_dim_b = fields.Selection(
        _DIM_SELECTION,
        string='Dimensión B', default='height',
        help='Dimensión del artículo que corresponde al segundo lado del panel de vidrio.',
    )
    # Los campos de deducción se reutilizan para A y B (compatibilidad hacia atrás).
    glass_width_deduction = fields.Float(
        'Deducción A (cm)', default=0.0,
        help='Centímetros a descontar de la Dimensión A del panel.'
    )
    glass_height_deduction = fields.Float(
        'Deducción B (cm)', default=0.0,
        help='Centímetros a descontar de la Dimensión B del panel.'
    )

    # --- Lineal: ahora soporta coeficiente de Largo (depth) ---
    width_coef = fields.Float('Coef. Ancho', default=0.0)
    height_coef = fields.Float('Coef. Alto', default=0.0)
    depth_coef = fields.Float('Coef. Largo', default=0.0)
    linear_constant = fields.Float('Constante (cm)', default=0.0)

    # ------------------------------------------------------------------ #

    @api.depends('material_product_id', 'material_product_id.display_name')
    def _compute_name(self):
        for rec in self:
            rec.name = rec.material_product_id.display_name or ''

    @api.depends(
        'material_type',
        'base_dimension', 'divisor', 'addition', 'deduction',
        'glass_dim_a', 'glass_dim_b', 'glass_width_deduction', 'glass_height_deduction',
        'width_coef', 'height_coef', 'depth_coef', 'linear_constant',
    )
    def _compute_formula_summary(self):
        for rec in self:
            mt = rec.material_type
            if mt == 'profile':
                if rec.base_dimension == 'fixed' or not rec.base_dimension:
                    rec.formula_summary = 'Fija'
                else:
                    dim = _DIM_LABEL.get(rec.base_dimension, '?')
                    div = rec.divisor or 1.0
                    base = ('%s/%g' % (dim, div)) if div != 1.0 else dim
                    adj = (rec.addition or 0.0) - (rec.deduction or 0.0)
                    if adj > 0:
                        rec.formula_summary = '%s +%g' % (base, adj)
                    elif adj < 0:
                        rec.formula_summary = '%s %g' % (base, adj)
                    else:
                        rec.formula_summary = base
            elif mt == 'glass':
                da_key = rec.glass_dim_a or 'width'
                db_key = rec.glass_dim_b or 'height'
                la = _DIM_LABEL.get(da_key, 'Ancho')
                lb = _DIM_LABEL.get(db_key, 'Alto')
                da = rec.glass_width_deduction or 0.0
                db = rec.glass_height_deduction or 0.0
                s = '%s×%s' % (la, lb)
                if da or db:
                    s += ' -%g/-%g' % (da, db)
                rec.formula_summary = s
            elif mt == 'linear':
                parts = []
                if rec.width_coef:
                    parts.append('%gA' % rec.width_coef)
                if rec.height_coef:
                    parts.append('%gH' % rec.height_coef)
                if rec.depth_coef:
                    parts.append('%gL' % rec.depth_coef)
                cst = rec.linear_constant or 0.0
                if parts:
                    s = 'Lineal ' + '+'.join(parts)
                    if cst:
                        s += '+%g' % cst if cst > 0 else '%g' % cst
                else:
                    s = 'Lineal %gcm' % cst
                rec.formula_summary = s
            elif mt == 'hardware':
                rec.formula_summary = 'Herraje'
            else:
                rec.formula_summary = ''

    # ------------------------------------------------------------------ #

    def get_unit(self):
        self.ensure_one()
        return UNIT_BY_TYPE.get(self.material_type, '')

    @staticmethod
    def _resolve_dim(width, height, depth, key):
        """Devuelve el valor de la dimensión indicada por key."""
        if key == 'height':
            return height
        if key == 'depth':
            return depth
        return width  # 'width' o default

    def compute_cut_result(self, width, height, depth=0.0):
        """
        Devuelve dict con los datos de corte para esta pieza.

        Claves comunes : size, unit
        Perfil         : solo size (cm)
        Vidrio         : cut_width/cut_height (compat.) + cut_a/cut_b + dim_a_label/dim_b_label
        Lineal         : size (m)
        Herraje        : size=None
        """
        self.ensure_one()
        unit = UNIT_BY_TYPE.get(self.material_type, '')

        if self.material_type == 'profile':
            if self.base_dimension == 'fixed' or not self.base_dimension:
                return {'size': None, 'unit': unit}
            dimension = self._resolve_dim(width, height, depth, self.base_dimension)
            divisor = self.divisor if self.divisor else 1.0
            size = round((dimension / divisor) + self.addition - self.deduction, 2)
            return {'size': size, 'unit': unit}

        if self.material_type == 'glass':
            da_key = self.glass_dim_a or 'width'
            db_key = self.glass_dim_b or 'height'
            dim_a = self._resolve_dim(width, height, depth, da_key)
            dim_b = self._resolve_dim(width, height, depth, db_key)
            cut_a = round(dim_a - (self.glass_width_deduction or 0.0), 2)
            cut_b = round(dim_b - (self.glass_height_deduction or 0.0), 2)
            area = round((cut_a / 100.0) * (cut_b / 100.0), 4)
            return {
                'size': area,
                'unit': unit,
                # Alias de compatibilidad (código y reportes existentes los usan)
                'cut_width': cut_a,
                'cut_height': cut_b,
                # Claves nuevas con nombre semántico
                'cut_a': cut_a,
                'cut_b': cut_b,
                'dim_a_label': _DIM_LABEL.get(da_key, 'Ancho'),
                'dim_b_label': _DIM_LABEL.get(db_key, 'Alto'),
            }

        if self.material_type == 'hardware':
            return {'size': None, 'unit': unit}

        if self.material_type == 'linear':
            largo_m = (
                (self.width_coef or 0.0) * width
                + (self.height_coef or 0.0) * height
                + (self.depth_coef or 0.0) * depth
                + (self.linear_constant or 0.0)
            ) / 100.0
            return {'size': round(largo_m, 3), 'unit': unit}

        return {'size': None, 'unit': unit}

    def compute_cut_size(self, width, height, depth=0.0):
        return self.compute_cut_result(width, height, depth)['size']
