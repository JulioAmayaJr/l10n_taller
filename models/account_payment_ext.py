from odoo import models, fields


class AccountPaymentExt(models.Model):
    _inherit = 'account.payment'

    vidrios_order_id = fields.Many2one(
        'vidrios.order',
        string='Orden de Taller',
        index=True,
        ondelete='set null',
    )
