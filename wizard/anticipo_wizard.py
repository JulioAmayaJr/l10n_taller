from odoo import models, fields, api, _
from odoo.exceptions import UserError


class VidriosAnticipoWizard(models.TransientModel):
    _name = 'vidrios.anticipo.wizard'
    _description = 'Wizard para registrar anticipo de orden de taller'

    order_id = fields.Many2one('vidrios.order', string='Orden', required=True)
    company_id = fields.Many2one(
        'res.company', related='order_id.company_id', readonly=True, store=False
    )
    currency_id = fields.Many2one(
        'res.currency', related='order_id.currency_id', readonly=True
    )
    amount = fields.Monetary('Monto del anticipo', required=True, currency_field='currency_id')
    journal_id = fields.Many2one(
        'account.journal',
        string='Método de pago',
        required=True,
        default=lambda self: self._default_journal_id(),
    )
    payment_date = fields.Date('Fecha de pago', default=fields.Date.today, required=True)
    memo = fields.Char('Referencia / Comprobante')

    order_total = fields.Monetary(related='order_id.amount_total', string='Total orden', readonly=True, currency_field='currency_id')
    order_paid = fields.Monetary(related='order_id.amount_paid', string='Ya pagado', readonly=True, currency_field='currency_id')
    order_due = fields.Monetary(related='order_id.amount_due', string='Saldo anterior', readonly=True, currency_field='currency_id')

    @api.model
    def _default_journal_id(self):
        """Diario de efectivo (cash) de la compañía activa como punto de partida."""
        return self.env['account.journal'].search(
            [('type', '=', 'cash'), ('company_id', '=', self.env.company.id)],
            limit=1,
        )

    @api.onchange('order_id')
    def _onchange_order_id(self):
        if self.order_id:
            self.amount = self.order_id.amount_due
            # Actualiza el diario default según la compañía de la orden
            if not self.journal_id or self.journal_id.company_id != self.order_id.company_id:
                company = self.order_id.company_id or self.env.company
                journal = self.env['account.journal'].search(
                    [('type', '=', 'cash'), ('company_id', '=', company.id)],
                    limit=1,
                )
                self.journal_id = journal

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
