from odoo import models, fields, api, _
from odoo.exceptions import UserError


ORDER_STATES = [
    ('draft', 'Borrador'),
    ('quoted', 'Cotizado'),
    ('deposit', 'Con anticipo'),
    ('production', 'En producción'),
    ('ready', 'Listo'),
    ('delivered', 'Entregado'),
    ('cancel', 'Cancelado'),
]


class VidriosOrder(models.Model):
    _name = 'vidrios.order'
    _description = 'Orden de Taller Vidrios Castillo'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(
        'Número', required=True, copy=False, readonly=True, default='Nuevo'
    )
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        related='company_id.currency_id', store=True, readonly=True
    )
    partner_id = fields.Many2one('res.partner', string='Cliente', tracking=True)
    quick_name = fields.Char('Nombre rápido', help='Para cotizar sin cliente registrado')
    quick_phone = fields.Char('Teléfono rápido')
    state = fields.Selection(
        ORDER_STATES, string='Estado', default='draft', required=True, tracking=True
    )

    line_ids = fields.One2many('vidrios.order.line', 'order_id', string='Líneas')
    extra_ids = fields.One2many('vidrios.extra', 'order_id', string='Extras')

    apply_tax = fields.Boolean('Aplicar IVA', default=False)
    tax_rate = fields.Float('Tasa IVA (%)', default=13.0)

    amount_untaxed = fields.Monetary(
        'Subtotal', compute='_compute_amounts', store=True,
        currency_field='currency_id'
    )
    amount_tax = fields.Monetary(
        'IVA', compute='_compute_amounts', store=True,
        currency_field='currency_id'
    )
    amount_total = fields.Monetary(
        'Total', compute='_compute_amounts', store=True,
        currency_field='currency_id'
    )
    amount_paid = fields.Monetary(
        'Anticipo pagado', compute='_compute_amounts', store=True,
        currency_field='currency_id'
    )
    amount_due = fields.Monetary(
        'Saldo pendiente', compute='_compute_amounts', store=True,
        currency_field='currency_id'
    )

    payment_ids = fields.One2many(
        'account.payment', 'vidrios_order_id', string='Anticipos'
    )

    delivery_date = fields.Date('Fecha de entrega prometida')
    notes = fields.Text('Observaciones')
    show_sp_detail = fields.Boolean(
        'Mostrar detalle SP / P1', default=False,
        help='Activa los recuadros SP/P1 en la Hoja de Ensamble'
    )
    photo_ids = fields.Many2many(
        'ir.attachment',
        'vidrios_order_attachment_rel',
        'order_id',
        'attachment_id',
        string='Fotos / Adjuntos',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('vidrios.order') or 'Nuevo'
                )
        return super().create(vals_list)

    @api.depends(
        'line_ids.price_subtotal',
        'extra_ids.price',
        'apply_tax',
        'tax_rate',
        'payment_ids.amount',
        'payment_ids.state',
    )
    def _compute_amounts(self):
        for order in self:
            lines_total = sum(order.line_ids.mapped('price_subtotal'))
            extras_total = sum(order.extra_ids.mapped('price'))
            subtotal = lines_total + extras_total
            tax = subtotal * (order.tax_rate / 100.0) if order.apply_tax else 0.0
            total = subtotal + tax
            paid = sum(
                p.amount for p in order.payment_ids
                if p.state in ('in_process', 'paid')
            )
            order.amount_untaxed = subtotal
            order.amount_tax = tax
            order.amount_total = total
            order.amount_paid = paid
            order.amount_due = total - paid

    # --- Flujo de estados ---

    def action_quote(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Solo se puede cotizar desde estado Borrador.'))
        self.write({'state': 'quoted'})

    def action_to_production(self):
        for rec in self:
            if rec.state not in ('quoted', 'deposit'):
                raise UserError(_('Debe estar cotizado o con anticipo para pasar a producción.'))
        self.write({'state': 'production'})

    def action_ready(self):
        for rec in self:
            if rec.state != 'production':
                raise UserError(_('Debe estar en producción para marcarlo como listo.'))
        self.write({'state': 'ready'})

    def action_delivered(self):
        for rec in self:
            if rec.state != 'ready':
                raise UserError(_('Debe estar listo para marcar como entregado.'))
        self.write({'state': 'delivered'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_draft(self):
        for rec in self:
            if rec.state not in ('cancel', 'quoted'):
                raise UserError(_('Solo se puede volver a borrador desde Cancelado o Cotizado.'))
        self.write({'state': 'draft'})

    def action_register_deposit(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Registrar Anticipo'),
            'res_model': 'vidrios.anticipo.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_amount': self.amount_due,
            },
        }

    def action_print_ticket(self):
        return self.env.ref(
            'vidrios_castillo_taller.action_report_ticket_cliente'
        ).report_action(self)

    def action_print_orden_interna(self):
        return self.env.ref(
            'vidrios_castillo_taller.action_report_orden_interna'
        ).report_action(self)

    def action_print_orden_interna_rollo(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/html/vidrios_castillo_taller.report_orden_interna_rollo/%s' % self.id,
            'target': 'new',
        }

    def action_print_ticket_rollo(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/html/vidrios_castillo_taller.report_ticket_rollo/%s' % self.id,
            'target': 'new',
        }

    # --- Helpers para reportes ---

    def get_print_info(self):
        """Devuelve dict {user, date} para el encabezado de la Hoja de Ensamble."""
        self.ensure_one()
        from odoo import fields as odoo_fields
        import pytz
        now_utc = odoo_fields.Datetime.now()
        tz_name = self.env.user.tz or 'UTC'
        try:
            tz = pytz.timezone(tz_name)
            now_local = pytz.utc.localize(now_utc).astimezone(tz)
        except Exception:
            now_local = now_utc
        return {
            'user': self.env.user.name or self.env.user.login,
            'date': now_local.strftime('%d/%m/%Y %H:%M'),
        }

    def get_display_name(self):
        self.ensure_one()
        return self.partner_id.name if self.partner_id else (self.quick_name or '')

    def get_display_phone(self):
        self.ensure_one()
        if self.partner_id:
            return self.partner_id.phone or self.partner_id.mobile or ''
        return self.quick_phone or ''

    def get_state_label(self):
        self.ensure_one()
        return dict(ORDER_STATES).get(self.state, self.state)
