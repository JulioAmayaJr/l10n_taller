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
    payment_method_id = fields.Many2one(
        'pos.payment.method',
        string='Método de pago',
        required=True,
        default=lambda self: self._default_payment_method_id(),
    )
    available_payment_method_ids = fields.Many2many(
        'pos.payment.method',
        compute='_compute_pos_session',
        store=False,
    )
    payment_date = fields.Date('Fecha de pago', default=fields.Date.today, required=True)
    memo = fields.Char('Referencia / Comprobante')

    order_total = fields.Monetary(related='order_id.amount_total', string='Total orden', readonly=True, currency_field='currency_id')
    order_paid = fields.Monetary(related='order_id.amount_paid', string='Ya pagado', readonly=True, currency_field='currency_id')
    order_due = fields.Monetary(related='order_id.amount_due', string='Saldo anterior', readonly=True, currency_field='currency_id')

    @api.model
    def _default_payment_method_id(self):
        session = self.env['pos.session'].sudo().search(
            [('state', '=', 'opened'), ('company_id', '=', self.env.company.id)],
            limit=1,
        )
        if session:
            return session.config_id.payment_method_ids[:1]
        return False

    @api.depends('order_id')
    def _compute_pos_session(self):
        for wizard in self:
            company = wizard.order_id.company_id or self.env.company
            session = self.env['pos.session'].sudo().search(
                [('state', '=', 'opened'), ('company_id', '=', company.id)],
                limit=1,
            )
            wizard.available_payment_method_ids = (
                session.config_id.payment_method_ids
                if session
                else self.env['pos.payment.method']
            )

    @api.onchange('order_id')
    def _onchange_order_id(self):
        if self.order_id:
            self.amount = self.order_id.amount_due
            company = self.order_id.company_id or self.env.company
            session = self.env['pos.session'].sudo().search(
                [('state', '=', 'opened'), ('company_id', '=', company.id)],
                limit=1,
            )
            if session:
                self.payment_method_id = session.config_id.payment_method_ids[:1]
                self.available_payment_method_ids = session.config_id.payment_method_ids
            else:
                self.payment_method_id = False
                self.available_payment_method_ids = self.env['pos.payment.method']

    def _get_pos_line_name(self, order):
        unique_products = order.line_ids.mapped('product_id')
        if len(unique_products) == 1:
            return _('Pago %s') % unique_products[0].name
        client_name = (
            order.partner_id.name if order.partner_id
            else (order.quick_name or order.name)
        )
        return _('Pago %s') % client_name

    def _get_or_create_partner(self, order):
        if order.partner_id:
            return order.partner_id
        name = order.quick_name or order.name
        partner = self.env['res.partner'].sudo().search([('name', '=', name)], limit=1)
        if not partner:
            partner = self.env['res.partner'].sudo().create({
                'name': name,
                'phone': order.quick_phone or '',
                'customer_rank': 1,
            })
        return partner

    def action_register(self):
        self.ensure_one()
        order = self.order_id
        company = order.company_id or self.env.company

        if self.amount <= 0:
            raise UserError(_('El monto del anticipo debe ser mayor a cero.'))

        pos_session = self.env['pos.session'].sudo().search(
            [('state', '=', 'opened'), ('company_id', '=', company.id)],
            limit=1,
        )
        if not pos_session:
            raise UserError(_(
                'No hay sesión POS abierta para la empresa "%s". '
                'Abre una sesión en el Punto de Venta antes de registrar el pago.'
            ) % company.name)

        pos_product = company.vidrios_pos_product_id
        if not pos_product:
            raise UserError(_(
                'No hay producto de pago configurado para la empresa "%s". '
                'Ve a Configuración → Empresa y configura el '
                '"Producto de pago taller (POS)".'
            ) % company.name)

        if self.payment_method_id not in pos_session.config_id.payment_method_ids:
            raise UserError(_(
                'El método de pago "%s" no pertenece a la sesión POS abierta.'
            ) % self.payment_method_id.name)

        partner = self._get_or_create_partner(order)
        line_name = self._get_pos_line_name(order)
        amount = self.amount

        pricelist_id = (
            pos_session.config_id.pricelist_id.id
            if pos_session.config_id.pricelist_id
            else False
        )

        pos_order = self.env['pos.order'].sudo().create({
            'session_id': pos_session.id,
            'company_id': company.id,
            'partner_id': partner.id,
            'pricelist_id': pricelist_id,
            'currency_id': pos_session.currency_id.id,
            'vidrios_order_id': order.id,
            'pos_reference': _('Taller/%s') % order.name,
            'note': order.name,
            'amount_total': amount,
            'amount_tax': 0.0,
            'amount_paid': amount,
            'amount_return': 0.0,
            'lines': [(0, 0, {
                'product_id': pos_product.id,
                'full_product_name': line_name,
                'qty': 1.0,
                'price_unit': amount,
                'price_subtotal': amount,
                'price_subtotal_incl': amount,
                'tax_ids': [(5, 0, 0)],
                'discount': 0.0,
            })],
        })

        self.env['pos.payment'].sudo().create({
            'pos_order_id': pos_order.id,
            'payment_method_id': self.payment_method_id.id,
            'amount': amount,
            'session_id': pos_session.id,
        })

        pos_order.sudo().action_pos_order_paid()

        if order.state in ('draft', 'quoted'):
            order.write({'state': 'deposit'})

        return {'type': 'ir.actions.act_window_close'}
