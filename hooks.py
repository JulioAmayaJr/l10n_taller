"""
post_init_hook + seed idempotente para integración de inventario.

Crea los productos de material, los enlaza a las fórmulas de demo_data
y carga stock inicial de prueba.  Es seguro correrlo varias veces.
"""
import logging

_logger = logging.getLogger(__name__)

MODULE = 'vidrios_castillo_taller'

# ---------------------------------------------------------------------------
# Catálogo de materiales a crear
# ---------------------------------------------------------------------------
# mtype: 'profile' | 'glass' | 'linear' | 'hardware'
MATERIAL_CATALOGUE = [
    # Perfiles (UoM = unidades; cada unidad = 1 barra de bar_length_cm)
    {'xmlid': 'mat_perfil_1504', 'default_code': '1504', 'name': 'Perfil 1504',
     'mtype': 'profile', 'bar_length_cm': 640.0, 'initial_stock': 50.0},
    {'xmlid': 'mat_perfil_1505', 'default_code': '1505', 'name': 'Perfil 1505',
     'mtype': 'profile', 'bar_length_cm': 640.0, 'initial_stock': 50.0},
    {'xmlid': 'mat_perfil_1506', 'default_code': '1506', 'name': 'Perfil 1506',
     'mtype': 'profile', 'bar_length_cm': 640.0, 'initial_stock': 50.0},
    {'xmlid': 'mat_perfil_1502', 'default_code': '1502', 'name': 'Perfil 1502',
     'mtype': 'profile', 'bar_length_cm': 640.0, 'initial_stock': 50.0},
    {'xmlid': 'mat_perfil_1509', 'default_code': '1509', 'name': 'Perfil 1509',
     'mtype': 'profile', 'bar_length_cm': 640.0, 'initial_stock': 50.0},
    {'xmlid': 'mat_perfil_1503', 'default_code': '1503', 'name': 'Perfil 1503',
     'mtype': 'profile', 'bar_length_cm': 640.0, 'initial_stock': 50.0},
    {'xmlid': 'mat_perfil_1508', 'default_code': '1508', 'name': 'Perfil 1508',
     'mtype': 'profile', 'bar_length_cm': 640.0, 'initial_stock': 50.0},
    {'xmlid': 'mat_perfil_1507', 'default_code': '1507', 'name': 'Perfil 1507',
     'mtype': 'profile', 'bar_length_cm': 640.0, 'initial_stock': 50.0},
    # Vidrio (UoM = m²)
    {'xmlid': 'mat_vidrio_claro_5mm', 'default_code': 'VCL5',
     'name': 'Vidrio Claro 5mm', 'mtype': 'glass', 'initial_stock': 100.0},
    # Herrajes (UoM = unidades)
    {'xmlid': 'mat_rodo', 'default_code': 'RODO', 'name': 'Rodo',
     'mtype': 'hardware', 'initial_stock': 500.0},
    {'xmlid': 'mat_cerrador', 'default_code': 'CERR', 'name': 'Cerrador',
     'mtype': 'hardware', 'initial_stock': 500.0},
    # Lineales (UoM = m)
    {'xmlid': 'mat_felpa', 'default_code': 'FELP', 'name': 'Felpa',
     'mtype': 'linear', 'initial_stock': 200.0},
    {'xmlid': 'mat_baquelita', 'default_code': 'BAQK', 'name': 'Baquelita',
     'mtype': 'linear', 'initial_stock': 200.0},
]

# ---------------------------------------------------------------------------
# Mapa fórmula → material
# (xmlid_formula, xmlid_material)
# Usa xmlids directamente — no depende del campo name (ahora computed).
# ---------------------------------------------------------------------------
FORMULA_LINKS = [
    # Ventana Francesa
    (f'{MODULE}.formula_vf_felpa',     'mat_felpa'),
    (f'{MODULE}.formula_vf_baquelita', 'mat_baquelita'),
    (f'{MODULE}.formula_vf_rodo',      'mat_rodo'),
    (f'{MODULE}.formula_vf_cerrador',  'mat_cerrador'),
    # Ventana corrediza (Puerta Corrediza)
    (f'{MODULE}.formula_ventana_riel_sup',  'mat_perfil_1504'),
    (f'{MODULE}.formula_ventana_riel_inf',  'mat_perfil_1504'),
    (f'{MODULE}.formula_ventana_jamba_izq', 'mat_perfil_1505'),
    (f'{MODULE}.formula_ventana_jamba_der', 'mat_perfil_1505'),
    (f'{MODULE}.formula_ventana_hoja_h',    'mat_perfil_1506'),
    (f'{MODULE}.formula_ventana_hoja_v',    'mat_perfil_1507'),
    (f'{MODULE}.formula_ventana_vidrio',    'mat_vidrio_claro_5mm'),
]

STOCK_LOADED_PARAM = f'{MODULE}.initial_stock_loaded_v1'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_uom(env, mtype):
    """Devuelve la UoM adecuada para el tipo de material."""
    if mtype == 'glass':
        for xmlid in ('uom.product_uom_sq_meter', 'uom.product_uom_square_meter'):
            try:
                return env.ref(xmlid)
            except ValueError:
                pass
        uom = env['uom.uom'].search(
            [('name', 'in', ['m²', 'm2', 'sq m', 'Square Meter', 'Metro cuadrado'])],
            limit=1,
        )
        if uom:
            return uom
        _logger.warning('No se encontró UoM m² — usando unidades')
        return env.ref('uom.product_uom_unit')

    if mtype == 'linear':
        try:
            return env.ref('uom.product_uom_meter')
        except ValueError:
            uom = env['uom.uom'].search(
                [('name', 'in', ['m', 'metros', 'Meter', 'Metro'])], limit=1
            )
            return uom or env.ref('uom.product_uom_unit')

    # profile y hardware → unidades
    return env.ref('uom.product_uom_unit')


def _get_or_create_product(env, entry):
    """
    Devuelve product.template existente (por xmlid) o lo crea.
    El xmlid garantiza idempotencia en reinstalaciones.
    """
    xmlid = entry['xmlid']
    full_xmlid = f'{MODULE}.{xmlid}'

    try:
        tmpl = env.ref(full_xmlid)
        _logger.debug('Producto ya existe: %s', full_xmlid)
        return tmpl
    except ValueError:
        pass

    uom = _find_uom(env, entry['mtype'])
    vals = {
        'name': entry['name'],
        'default_code': entry['default_code'],
        'type': 'product',          # almacenable (con stock)
        'uom_id': uom.id,
        'uom_po_id': uom.id,
        'purchase_ok': True,
        'sale_ok': False,
        'bar_length_cm': entry.get('bar_length_cm', 0.0),
    }
    tmpl = env['product.template'].sudo().create(vals)

    env['ir.model.data'].sudo().create({
        'name': xmlid,
        'module': MODULE,
        'model': 'product.template',
        'res_id': tmpl.id,
        'noupdate': True,
    })
    _logger.info('Producto creado: %s (%s)', entry['name'], entry['default_code'])
    return tmpl


def _load_initial_stock(env, product_tmpl, qty):
    """Carga stock inicial usando stock.quant._update_available_quantity."""
    warehouse = env['stock.warehouse'].sudo().search(
        [('company_id', '=', env.company.id)], limit=1
    )
    if not warehouse:
        _logger.warning('No hay almacén configurado — se omite carga de stock inicial')
        return

    location = warehouse.lot_stock_id
    variant = product_tmpl.product_variant_id
    if not variant:
        _logger.warning('Producto sin variante: %s', product_tmpl.name)
        return

    env['stock.quant'].sudo()._update_available_quantity(variant, location, qty)
    _logger.info('Stock inicial cargado: %s × %.2f en %s', variant.name, qty, location.name)


# ---------------------------------------------------------------------------
# Función principal del seed (idempotente)
# ---------------------------------------------------------------------------

def _seed_data(env):
    """
    Crea materiales, enlaza fórmulas y carga stock inicial.
    Seguro de llamar varias veces; no duplica datos.
    """
    # 1. Crear / recuperar productos de material
    created_tmpl = {}
    for entry in MATERIAL_CATALOGUE:
        tmpl = _get_or_create_product(env, entry)
        created_tmpl[entry['xmlid']] = tmpl

    # 2. Enlazar fórmulas → material_product_id (usando xmlids, no nombres)
    for formula_xmlid, mat_xmlid in FORMULA_LINKS:
        try:
            formula = env.ref(formula_xmlid)
        except ValueError:
            _logger.warning('Fórmula no encontrada: %s', formula_xmlid)
            continue

        mat_tmpl = created_tmpl.get(mat_xmlid)
        if not mat_tmpl:
            _logger.warning('Material no encontrado para xmlid: %s', mat_xmlid)
            continue

        variant = mat_tmpl.product_variant_id
        if not variant:
            continue

        if formula.material_product_id.id != variant.id:
            formula.sudo().write({'material_product_id': variant.id})
            _logger.info('Enlace: %s → %s', formula_xmlid, mat_tmpl.name)

    # 3. Sincronizar opciones de características (idempotente)
    _logger.info('Sincronizando opciones de características…')
    select_chars = env['vidrios.characteristic'].sudo().search([
        ('field_type', '=', 'select'),
    ])
    select_chars._sync_options()
    _logger.info('Opciones sincronizadas para %d características', len(select_chars))

    # 4. Carga stock inicial (sólo una vez)
    param = env['ir.config_parameter'].sudo()
    if not param.get_param(STOCK_LOADED_PARAM):
        for entry in MATERIAL_CATALOGUE:
            tmpl = created_tmpl.get(entry['xmlid'])
            if tmpl and entry.get('initial_stock', 0) > 0:
                _load_initial_stock(env, tmpl, entry['initial_stock'])
        param.set_param(STOCK_LOADED_PARAM, '1')
        _logger.info('Stock inicial cargado correctamente')
    else:
        _logger.info('Stock inicial ya cargado — se omite (param: %s)', STOCK_LOADED_PARAM)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def post_init_hook(env):
    """Llamado automáticamente tras la instalación del módulo."""
    _logger.info('post_init_hook: ejecutando seed de inventario…')
    _seed_data(env)
