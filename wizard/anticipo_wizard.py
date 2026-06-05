from odoo import models, fields, api, _
from odoo.exceptions import UserError


class VidriosAnticipoWizard(models.TransientModel):
    _name = 'vidrios.anticipo.wizard'
    _description = 'Wizard para registrar anticipo de orden de taller'

    order_id = fields.Many2one('vidrios.order', string='Orden', required=True)
    currency_id = fields.Many2one(
        'res.currency', related='order_id.currency_id', readonly=True
    )
    amount = fields.Monetary('Monto del anticipo', required=True, currency_field='currency_id')
    journal_id = fields.Many2one(
        'account.journal',
        string='Caja / Banco',
        required=True,
        domain=[('type', 'in', ['bank', 'cash'])],
    )
    payment_date = fields.Date('Fecha de pago', default=fields.Date.today, required=True)
    memo = fields.Char('Referencia / Comprobante')

    order_total = fields.Monetary(related='order_id.amount_total', string='Total orden', readonly=True, currency_field='currency_id')
    order_paid = fields.Monetary(related='order_id.amount_paid', string='Ya pagado', readonly=True, currency_field='currency_id')
    order_due = fields.Monetary(related='order_id.amount_due', string='Saldo anterior', readonly=True, currency_field='currency_id')

    @api.onchange('order_id')
    def _onchange_order_id(self):
        if self.order_id:
            self.amount = self.order_id.amount_due

    def action_register(self):
        self.ensure_one()
        order = self.order_id

        if self.amount <= 0:
            raise UserError(_('El monto del anticipo debe ser mayor a cero.'))

        partner = order.partner_id
        if not partner:
            partner = self.env['res.partner'].search(
                [('name', '=', order.quick_name or order.name)], limit=1
            )
            if not partner:
                partner = self.env['res.partner'].create({
                    'name': order.quick_name or order.name,
                    'phone': order.quick_phone or '',
                    'customer_rank': 1,
                })

        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': partner.id,
            'amount': self.amount,
            'journal_id': self.journal_id.id,
            'date': self.payment_date,
            'memo': self.memo or _('Anticipo %s') % order.name,
            'vidrios_order_id': order.id,
        })
        payment.action_post()

        if order.state in ('draft', 'quoted'):
            order.write({'state': 'deposit'})

        return {'type': 'ir.actions.act_window_close'}
