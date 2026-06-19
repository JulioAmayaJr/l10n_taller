from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class VidriosProduct(models.Model):
    _name = 'vidrios.product'
    _description = 'Tipo de Producto Vidrios Castillo'
    _order = 'name'

    name = fields.Char('Nombre', required=True)
    active = fields.Boolean('Activo', default=True)
    price_m2 = fields.Float('Precio por m²', digits=(10, 2), default=0.0)
    min_price = fields.Float('Precio mínimo', digits=(10, 2), default=0.0)
    requires_depth = fields.Boolean(
        'Requiere Largo (3D)',
        default=False,
        help='Activa el campo Largo (cm) en las líneas de orden para productos 3D '
             '(ej. vitrinas, peceras, acuarios). Las fórmulas pueden usar Largo como '
             'dimensión base de paneles y perfiles.',
    )
    characteristic_ids = fields.One2many(
        'vidrios.characteristic', 'product_id', string='Características'
    )
    formula_ids = fields.One2many(
        'vidrios.formula', 'product_id', string='Fórmulas de despiece'
    )
    modulo_ids = fields.Many2many(
        'vidrios.product',
        relation='vidrios_product_modulo_rel',
        column1='product_id',
        column2='modulo_id',
        string='Módulos / Complementos',
        help='Otros productos cuyas piezas se suman al despiece de este. '
             'Ej.: añadir "Mosquitero" a "Ventana Francesa" genera también las piezas del mosquitero.',
    )

    # ------------------------------------------------------------------ #

    @api.constrains('modulo_ids')
    def _check_no_self_modulo(self):
        for product in self:
            if product in product.modulo_ids:
                raise ValidationError(
                    _('El producto "%s" no puede incluirse a sí mismo como módulo.')
                    % product.name
                )

    def _get_all_formulas(self, visited=None):
        """
        Devuelve todas las fórmulas a aplicar en el despiece:
        las propias (ordenadas por sequence) + las de cada módulo en modulo_ids,
        de forma recursiva. El set 'visited' evita ciclos (A→B→A).
        """
        if visited is None:
            visited = set()
        if self.id in visited:
            return self.env['vidrios.formula']
        visited.add(self.id)

        # Fórmulas propias primero, luego las de cada módulo en orden
        result = self.formula_ids.sorted('sequence')
        for modulo in self.modulo_ids:
            result = result | modulo._get_all_formulas(visited)
        return result
