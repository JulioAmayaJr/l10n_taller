from odoo import models, fields


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


class VidriosFormula(models.Model):
    _name = 'vidrios.formula'
    _description = 'Fórmula de Despiece Paramétrica'
    _order = 'product_id, sequence, name'

    product_id = fields.Many2one(
        'vidrios.product', string='Producto', required=True, ondelete='cascade'
    )
    name = fields.Char('Pieza', required=True, help='Ej: Riel superior, Vidrio interior')
    sequence = fields.Integer('Secuencia', default=10)
    material_type = fields.Selection(
        MATERIAL_TYPE, string='Tipo de material', required=True, default='profile'
    )
    quantity = fields.Integer('Cantidad', default=1)
    material_code = fields.Char(
        'Código', help='Código del material en inventario (para hoja de ensamble)'
    )
    notes = fields.Char('Notas')

    # --- Campos para Perfil (profile) ---
    base_dimension = fields.Selection(
        [('width', 'Ancho'), ('height', 'Alto'), ('fixed', 'Fija')],
        string='Dimensión base', default='width'
    )
    divisor = fields.Float('Divisor', default=1.0)
    addition = fields.Float('Adición (cm)', default=0.0)
    deduction = fields.Float('Deducción (cm)', default=0.0)

    # --- Campos para Vidrio (glass) ---
    glass_width_deduction = fields.Float(
        'Deduc. Ancho (cm)', default=0.0,
        help='Centímetros a descontar del ancho para obtener el corte de vidrio'
    )
    glass_height_deduction = fields.Float(
        'Deduc. Alto (cm)', default=0.0,
        help='Centímetros a descontar del alto para obtener el corte de vidrio'
    )

    # --- Campos para Lineal (linear) ---
    width_coef = fields.Float('Coef. Ancho', default=0.0,
        help='Multiplicador del ancho (cm) para calcular metros lineales')
    height_coef = fields.Float('Coef. Alto', default=0.0,
        help='Multiplicador del alto (cm) para calcular metros lineales')
    linear_constant = fields.Float('Constante (cm)', default=0.0,
        help='Valor fijo sumado antes de convertir a metros')

    def get_unit(self):
        self.ensure_one()
        return UNIT_BY_TYPE.get(self.material_type, '')

    def compute_cut_result(self, width, height):
        """
        Devuelve dict con los datos de corte para esta pieza.

        Claves comunes:   size, unit
        Solo glass:       cut_width, cut_height  (medidas reales de corte en cm)

        Tipos:
        - profile  : (base/divisor)+addition-deduction            → cm
        - glass    : corte_w = w - deduccion_w
                     corte_h = h - deduccion_h
                     area    = (corte_w/100)*(corte_h/100)        → m²
        - hardware : sin medida, solo cantidad                    → uds
        - linear   : (width_coef*w + height_coef*h + cte)/100    → m
        """
        self.ensure_one()
        unit = UNIT_BY_TYPE.get(self.material_type, '')

        if self.material_type == 'profile':
            if self.base_dimension == 'fixed' or not self.base_dimension:
                return {'size': None, 'unit': unit}
            dimension = width if self.base_dimension == 'width' else height
            divisor = self.divisor if self.divisor else 1.0
            size = round((dimension / divisor) + self.addition - self.deduction, 2)
            return {'size': size, 'unit': unit}

        if self.material_type == 'glass':
            cut_w = round(width - self.glass_width_deduction, 2)
            cut_h = round(height - self.glass_height_deduction, 2)
            area = round((cut_w / 100.0) * (cut_h / 100.0), 4)
            return {
                'size': area,
                'unit': unit,
                'cut_width': cut_w,
                'cut_height': cut_h,
            }

        if self.material_type == 'hardware':
            return {'size': None, 'unit': unit}

        if self.material_type == 'linear':
            largo_m = (
                self.width_coef * width
                + self.height_coef * height
                + self.linear_constant
            ) / 100.0
            return {'size': round(largo_m, 3), 'unit': unit}

        return {'size': None, 'unit': unit}

    # Alias de compatibilidad — devuelve solo el valor numérico
    def compute_cut_size(self, width, height):
        return self.compute_cut_result(width, height)['size']
