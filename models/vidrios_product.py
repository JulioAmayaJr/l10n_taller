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
    use_fixed_price = fields.Boolean('Precio fijo', default=False)
    fixed_price = fields.Float('Precio fijo ($)', digits=(10, 2), default=0.0)
    requires_depth = fields.Boolean(
        'Requiere Largo (3D)',
        default=False,
        help='Activa el campo Largo (cm) en las líneas de orden para productos 3D '
             '(ej. vitrinas, peceras, acuarios). Las fórmulas pueden usar Largo como '
             'dimensión base de paneles y perfiles.',
    )
    characteristic_ids = fields.One2many(
        'vidrios.characteristic', 'product_id', string='Características', copy=True
    )
    formula_ids = fields.One2many(
        'vidrios.formula', 'product_id', string='Fórmulas de despiece', copy=True
    )
    price_tier_ids = fields.One2many(
        'vidrios.price.tier', 'product_id', string='Precios por rango', copy=True
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

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        if 'name' in (default or {}):
            return vals_list
        return [
            dict(vals, name=_('%s (copia)') % record.name)
            for record, vals in zip(self, vals_list)
        ]

    def get_price_for_area(self, area):
        """
        Precio unitario para el área dada.

        1. use_fixed_price activo → devuelve fixed_price (ignora área, tiers y price_m2).
        2. price_tier_ids definidos → toma el ÚLTIMO tier con min_area <= area
           (semántica "landing"). Si el área cae antes del primero, usa el primero.
             - 'fixed'  → devuelve amount
             - 'per_m2' → devuelve area * amount
        3. Sin tiers → max(area * price_m2, min_price).
        """
        self.ensure_one()
        if self.use_fixed_price:
            return self.fixed_price

        tiers = self.price_tier_ids.sorted('min_area')
        if not tiers:
            return max(area * self.price_m2, self.min_price)

        applicable = tiers[0]
        for tier in tiers:
            if tier.min_area <= area:
                applicable = tier

        if applicable.price_mode == 'fixed':
            return applicable.amount
        return area * applicable.amount

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
