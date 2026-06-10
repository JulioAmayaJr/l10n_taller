from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    bar_length_cm = fields.Float(
        'Largo de barra (cm)',
        default=640.0,
        help='Longitud estándar de la barra/perfil. '
             'Se usa para calcular cuántas barras consume un corte de perfil.',
    )
