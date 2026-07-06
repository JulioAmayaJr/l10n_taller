import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

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
    pos_order_ids = fields.One2many(
        'pos.order', 'vidrios_order_id', string='Pedidos POS'
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

    # ------------------------------------------------------------------ #
    # Integración Inventario                                               #
    # ------------------------------------------------------------------ #

    material_ids = fields.One2many(
        'vidrios.order.material', 'order_id', string='Materiales estimados'
    )
    used_material_ids = fields.One2many(
        'vidrios.order.material.used', 'order_id', string='Materiales usados'
    )
    consume_stock = fields.Boolean(
        'Consumir stock al producir (inmediato)', default=False,
        help='Si está activo, al pasar a Producción se descuenta el inventario de inmediato '
             'usando los estimados. Si está inactivo (recomendado), el descuento ocurre '
             'al marcar la orden como Lista, usando los materiales realmente usados.',
    )
    stock_consumed = fields.Boolean(
        'Stock consumido', default=False, copy=False, readonly=True,
        help='Marca interna: evita descontar el stock dos veces.',
    )
    stock_move_ids = fields.One2many(
        'stock.move', 'vidrios_order_id', string='Movimientos de stock'
    )

    # ------------------------------------------------------------------ #
    # Secuencia                                                            #
    # ------------------------------------------------------------------ #

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('vidrios.order') or 'Nuevo'
                )
        orders = super().create(vals_list)
        orders._recompute_materials()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if 'line_ids' in vals:
            self._recompute_materials()
        return res

    # ------------------------------------------------------------------ #
    # Montos                                                               #
    # ------------------------------------------------------------------ #

    @api.depends(
        'line_ids.price_subtotal',
        'extra_ids.price',
        'apply_tax',
        'tax_rate',
        'payment_ids.amount',
        'payment_ids.state',
        'pos_order_ids.state',
        'pos_order_ids.payment_ids.amount',
    )
    def _compute_amounts(self):
        for order in self:
            lines_total = sum(order.line_ids.mapped('price_subtotal'))
            extras_total = sum(order.extra_ids.mapped('price'))
            subtotal = lines_total + extras_total
            tax = subtotal * (order.tax_rate / 100.0) if order.apply_tax else 0.0
            total = subtotal + tax
            paid = sum(
                p.amount for p in order.sudo().payment_ids
                if p.state in ('in_process', 'paid')
            )
            for pos_ord in order.pos_order_ids.sudo():
                if pos_ord.state in ('paid', 'done', 'invoiced'):
                    paid += sum(pos_ord.payment_ids.mapped('amount'))
            order.amount_untaxed = subtotal
            order.amount_tax = tax
            order.amount_total = total
            order.amount_paid = paid
            order.amount_due = total - paid

    def _get_report_payments(self):
        self.ensure_one()
        return self.sudo().payment_ids.filtered(
            lambda p: p.state in ('in_process', 'paid')
        )

    def _get_report_company(self):
        self.ensure_one()
        return self.sudo().company_id

    # ------------------------------------------------------------------ #
    # Flujo de estados                                                     #
    # ------------------------------------------------------------------ #

    def action_quote(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Solo se puede cotizar desde estado Borrador.'))
        self.write({'state': 'quoted'})

    def action_to_production(self):
        for rec in self:
            if rec.state not in ('quoted', 'deposit'):
                raise UserError(_('Debe estar cotizado o con anticipo para pasar a producción.'))
            rec._recompute_materials()
            # Pre-carga "Materiales usados" desde los estimados si aún está vacío
            rec._prefill_used_materials()
            # Consumo inmediato al producir solo si la opción legacy está activa
            if rec.consume_stock and not rec.stock_consumed:
                rec._generate_stock_moves()
        self.write({'state': 'production'})

    def action_ready(self):
        for rec in self:
            if rec.state != 'production':
                raise UserError(_('Debe estar en producción para marcarlo como listo.'))
            # Descuenta inventario con los materiales USADOS (editados por el usuario)
            if not rec.stock_consumed:
                rec._generate_stock_moves_from_used()
        self.write({'state': 'ready'})

    def action_delivered(self):
        for rec in self:
            if rec.state != 'ready':
                raise UserError(_('Debe estar listo para marcar como entregado.'))
            # Robustez: descuenta si por algún flujo llegó aquí sin consumir
            if not rec.stock_consumed:
                rec._generate_stock_moves_from_used()
        self.write({'state': 'delivered'})

    def action_cancel(self):
        for rec in self:
            if rec.stock_consumed:
                rec._revert_stock_moves()
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

    # ------------------------------------------------------------------ #
    # Materiales estimados                                                 #
    # ------------------------------------------------------------------ #

    def _get_materials_summary(self):
        """
        Calcula el consumo de materiales agrupado por material_product_id.
        Devuelve lista de dicts: {product, qty, uom, name}.

        Reglas de agrupación:
        - Perfil  → total_cm / bar_length_cm  (barras con decimales)
        - Vidrio  → suma de áreas (m²)
        - Lineal  → suma de metros (m)
        - Herraje → suma de unidades (uds)
        """
        self.ensure_one()
        aggregated = {}  # product.id → {product, qty, uom, name}

        for line in self.line_ids:
            for _source, formulas in line._get_formulas_by_source():
                for formula in formulas:
                    if not formula.material_product_id:
                        continue

                    product = formula.material_product_id
                    cut = formula.compute_cut_result(line.width, line.height, line.depth)
                    pieces_per_line = formula.quantity * line.quantity

                    mtype = formula.material_type
                    if mtype == 'profile':
                        if cut['size'] is None:
                            continue
                        total_cm = cut['size'] * pieces_per_line
                        bar_len = product.bar_length_cm or 640.0
                        qty = total_cm / bar_len
                        uom = 'barras'

                    elif mtype == 'glass':
                        if cut['size'] is None:
                            continue
                        qty = cut['size'] * pieces_per_line
                        uom = 'm²'

                    elif mtype == 'linear':
                        if cut['size'] is None:
                            continue
                        qty = cut['size'] * pieces_per_line
                        uom = 'm'

                    elif mtype == 'hardware':
                        qty = pieces_per_line
                        uom = 'uds'

                    else:
                        continue

                    pid = product.id
                    if pid not in aggregated:
                        aggregated[pid] = {
                            'product': product,
                            'qty': 0.0,
                            'uom': uom,
                            'name': product.display_name,
                        }
                    aggregated[pid]['qty'] += qty

        return list(aggregated.values())

    def _recompute_materials(self):
        """Regenera los registros vidrios.order.material de esta orden."""
        for order in self:
            order.material_ids.sudo().unlink()
            materials = order._get_materials_summary()
            if not materials:
                continue
            vals_list = [
                {
                    'order_id': order.id,
                    'product_id': mat['product'].id,
                    'qty_needed': round(mat['qty'], 4),
                    'uom_name': mat['uom'],
                }
                for mat in materials
                if mat['qty'] > 0
            ]
            if vals_list:
                self.env['vidrios.order.material'].sudo().create(vals_list)

    def action_recompute_materials(self):
        """Botón manual de recálculo de estimados."""
        self._recompute_materials()

    def action_reload_used_from_estimated(self):
        """Sobreescribe 'Materiales usados' con los estimados actuales."""
        for order in self:
            order.used_material_ids.sudo().unlink()
            order._recompute_materials()
            order._prefill_used_materials()

    # ------------------------------------------------------------------ #
    # Descuento automático de stock                                        #
    # ------------------------------------------------------------------ #

    def _get_stock_locations(self):
        """Devuelve (ubicación_origen, ubicación_destino_producción) para la empresa de la orden."""
        company = self.company_id or self.env.company

        warehouse = self.env['stock.warehouse'].sudo().search(
            [('company_id', '=', company.id)], limit=1
        )
        if not warehouse:
            raise UserError(_(
                'No se encontró almacén configurado para la empresa "%s".'
            ) % company.name)

        location_src = warehouse.lot_stock_id

        location_dest = self.env['stock.location'].sudo().search(
            [('usage', '=', 'production'), ('company_id', '=', company.id)],
            limit=1,
        )
        if not location_dest:
            raise UserError(_(
                'No se encontró la ubicación virtual de Producción '
                'para la empresa "%s".'
            ) % company.name)

        return location_src, location_dest

    def _generate_stock_moves(self):
        """
        Crea stock.move por cada material estimado y los marca como hechos.
        Fuente: almacén interno.  Destino: ubicación virtual de Producción.
        """
        self.ensure_one()
        materials = self._get_materials_summary()
        if not materials:
            self.stock_consumed = True
            return

        location_src, location_dest = self._get_stock_locations()

        move_vals_list = []
        for mat in materials:
            qty = round(mat['qty'], 4)
            if qty <= 0:
                continue
            move_vals_list.append({
                # 'name' no existe en stock.move de Odoo 19; usar description_picking_manual
                'description_picking_manual': 'Consumo %s — %s' % (self.name, mat['name']),
                'product_id': mat['product'].id,
                'product_uom_qty': qty,
                'product_uom': mat['product'].uom_id.id,
                'location_id': location_src.id,
                'location_dest_id': location_dest.id,
                'origin': self.name,
                'company_id': self.company_id.id,
                'vidrios_order_id': self.id,
            })

        if not move_vals_list:
            self.stock_consumed = True
            return

        moves = self.env['stock.move'].sudo().create(move_vals_list)
        moves.sudo()._action_confirm()
        moves.sudo()._action_assign()

        # En Odoo 19 _action_done cancela el move si picked=False; hay que setearlo.
        for move in moves.sudo():
            move.quantity = move.product_uom_qty  # crea move lines con la qty hecha
            move.picked = True                     # marca líneas como pickeadas

        moves.sudo()._action_done()

        self.sudo().write({'stock_consumed': True})
        _logger.info('Stock consumido para orden %s (%d movimientos)', self.name, len(moves))

    def _prefill_used_materials(self):
        """
        Copia los materiales estimados a 'Materiales usados' como punto de partida editable.
        Solo actúa si la lista está vacía (no sobreescribe ediciones del usuario).
        """
        self.ensure_one()
        if self.used_material_ids:
            return
        vals_list = [
            {
                'order_id': self.id,
                'product_id': mat.product_id.id,
                'qty_used': mat.qty_needed,
                'uom_name': mat.uom_name,
            }
            for mat in self.material_ids
            if mat.qty_needed > 0
        ]
        if vals_list:
            self.env['vidrios.order.material.used'].sudo().create(vals_list)

    def _generate_stock_moves_from_used(self):
        """
        Crea stock.move por cada material de la lista USADA (editable) y los marca como hechos.
        Fuente: almacén interno.  Destino: ubicación virtual de Producción.
        """
        self.ensure_one()
        if not self.used_material_ids:
            self.stock_consumed = True
            return

        location_src, location_dest = self._get_stock_locations()

        move_vals_list = []
        for mat in self.used_material_ids:
            qty = round(mat.qty_used, 4)
            if qty <= 0:
                continue
            move_vals_list.append({
                'description_picking_manual': 'Consumo %s — %s' % (self.name, mat.product_id.display_name),
                'product_id': mat.product_id.id,
                'product_uom_qty': qty,
                'product_uom': mat.product_id.uom_id.id,
                'location_id': location_src.id,
                'location_dest_id': location_dest.id,
                'origin': self.name,
                'company_id': self.company_id.id,
                'vidrios_order_id': self.id,
            })

        if not move_vals_list:
            self.stock_consumed = True
            return

        moves = self.env['stock.move'].sudo().create(move_vals_list)
        moves.sudo()._action_confirm()
        moves.sudo()._action_assign()
        for move in moves.sudo():
            move.quantity = move.product_uom_qty
            move.picked = True
        moves.sudo()._action_done()

        self.sudo().write({'stock_consumed': True})
        _logger.info('Stock consumido (usados) para orden %s (%d movimientos)', self.name, len(moves))

    def _revert_stock_moves(self):
        """
        Crea movimientos inversos para reponer el material al almacén.
        Se llama cuando la orden se Cancela y ya tiene stock_consumed=True.
        """
        self.ensure_one()
        done_moves = self.stock_move_ids.filtered(lambda m: m.state == 'done')
        if not done_moves:
            self.stock_consumed = False
            return

        location_src, location_dest = self._get_stock_locations()

        return_vals = []
        for move in done_moves:
            qty = move.quantity
            if qty <= 0:
                continue
            return_vals.append({
                'description_picking_manual': 'Dev. %s — %s' % (self.name, move.product_id.display_name),
                'product_id': move.product_id.id,
                'product_uom_qty': qty,
                'product_uom': move.product_uom.id,
                'location_id': location_dest.id,      # invertido: desde producción
                'location_dest_id': location_src.id,  # hacia stock
                'origin': 'Cancel: %s' % self.name,
                'company_id': self.company_id.id,
                'vidrios_order_id': self.id,
                'origin_returned_move_id': move.id,
            })

        if not return_vals:
            self.stock_consumed = False
            return

        rev_moves = self.env['stock.move'].sudo().create(return_vals)
        rev_moves.sudo()._action_confirm()
        for move in rev_moves.sudo():
            move.quantity = move.product_uom_qty
            move.picked = True
        rev_moves.sudo()._action_done()

        self.sudo().write({'stock_consumed': False})
        _logger.info('Stock revertido para orden %s', self.name)

    # ------------------------------------------------------------------ #
    # Acción "Cargar datos de prueba" (menú)                              #
    # ------------------------------------------------------------------ #

    @api.model
    def action_seed_data(self):
        from ..hooks import _seed_data
        _seed_data(self.env)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Datos de prueba'),
                'message': _('Materiales creados, fórmulas enlazadas y stock cargado correctamente.'),
                'sticky': False,
                'type': 'success',
            },
        }

    # ------------------------------------------------------------------ #
    # Acciones de impresión                                                #
    # ------------------------------------------------------------------ #

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

    # ------------------------------------------------------------------ #
    # Helpers para reportes                                                #
    # ------------------------------------------------------------------ #

    def get_print_info(self):
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
        if self.partner_id and self.partner_id.phone:
            return self.partner_id.phone
        return self.quick_phone or ''

    def get_state_label(self):
        self.ensure_one()
        return dict(ORDER_STATES).get(self.state, self.state)
