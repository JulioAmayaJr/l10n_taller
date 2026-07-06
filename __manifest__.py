{
    'name': 'Vidrios Castillo Taller',
    'version': '19.0.1.0.0',
    'summary': 'Gestión de taller de vidrios y aluminio para Vidrios Castillo',
    'description': '''
        Sistema de gestión de taller para Vidrios Castillo.
        Cotizaciones, anticipos, producción y entrega de trabajos
        de vidrio y aluminio con despiece paramétrico.
    ''',
    'author': 'Vidrios Castillo',
    'category': 'Manufacturing',
    'license': 'LGPL-3',
    'application': True,
    'installable': True,
    'depends': ['base', 'mail', 'account', 'stock', 'point_of_sale'],
    'post_init_hook': 'post_init_hook',
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'data/demo_data.xml',
        'data/init_options.xml',
        'wizard/anticipo_wizard_views.xml',
        'views/vidrios_company_views.xml',
        'views/vidrios_product_views.xml',
        'views/vidrios_order_views.xml',
        'views/vidrios_report_views.xml',
        'report/ticket_cliente.xml',
        'report/orden_interna.xml',
        'report/orden_interna_rollo.xml',
        'views/menus.xml',
    ],
    'images': ['static/description/icon.png'],
}
