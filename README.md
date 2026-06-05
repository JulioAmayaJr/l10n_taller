# Vidrios Castillo Taller — Módulo Odoo 19 Enterprise

Sistema de gestión de taller de vidrios y aluminio para **Vidrios Castillo**.

## Características

- Cotizaciones con líneas de producto, medidas y características configurables
- Despiece / lista de corte generada en vivo desde fórmulas paramétricas
- Registro de anticipos como `account.payment` real (integrado a contabilidad)
- Flujo de estados: Borrador → Cotizado → Con anticipo → Producción → Listo → Entregado
- Reportes PDF: Ticket Cliente y Orden Interna de Taller
- 4 grupos de seguridad con permisos diferenciados

## Instalación

1. Copiar la carpeta `vidrios_castillo_taller` en el directorio `addons` de Odoo.
2. Actualizar la lista de módulos (modo desarrollador → Aplicaciones → Actualizar lista).
3. Buscar "Vidrios Castillo Taller" e instalar.

## Grupos de seguridad

| Grupo | Permisos |
|---|---|
| **Administrador** | Acceso total: crear/editar productos, precios, fórmulas; cancelar órdenes; ver todo |
| **Vendedor** | Crear cotizaciones, registrar anticipos, imprimir ticket cliente |
| **Taller** | Ver medidas y despiece, cambiar estado de producción (no ve precios) |
| **Caja / Administración** | Ver pagos, saldos y anticipos |

## Estructura del módulo

```
vidrios_castillo_taller/
├── models/
│   ├── vidrios_product.py          — Tipos de producto (Ventana, Vitrina, etc.)
│   ├── vidrios_characteristic.py   — Características configurables por producto
│   ├── vidrios_formula.py          — Fórmulas paramétricas de despiece
│   ├── vidrios_order.py            — Orden de taller (cabecera)
│   ├── vidrios_order_line.py       — Líneas de cotización
│   ├── vidrios_order_line_characteristic.py — Valores de características por línea
│   ├── vidrios_extra.py            — Extras (flete, instalación, etc.)
│   └── account_payment_ext.py      — Extensión de account.payment con link a orden
├── wizard/
│   └── anticipo_wizard.py          — Wizard para registrar anticipo
├── views/                          — Vistas list/form/kanban/search
├── report/
│   ├── ticket_cliente.xml          — PDF: Ticket para el cliente
│   └── orden_interna.xml           — PDF: Orden interna con despiece
├── security/
│   ├── security.xml                — Grupos de seguridad
│   └── ir.model.access.csv         — Permisos de acceso por modelo
└── data/
    ├── sequences.xml               — Secuencia T-#####
    └── demo_data.xml               — Productos de ejemplo con características y fórmulas
```

## Cálculo de precios

- **Área** = (Ancho / 100) × (Alto / 100) en m²
- **Precio unitario** = `max(área × precio_m2, precio_mínimo)`
- **Subtotal línea** = precio_unitario × cantidad
- **Total** = Σ líneas + Σ extras + IVA (si aplica)
- **Saldo** = Total − Anticipos pagados (estado `posted`)

## Cálculo de despiece

Para cada fórmula del producto aplicada a las medidas de la línea:

- `base_dimension = width` → `(ancho / divisor) + adición − deducción`
- `base_dimension = height` → `(alto / divisor) + adición − deducción`
- `base_dimension = fixed` → medida fija (sin dimensión)

La cantidad final = `fórmula.quantity × línea.quantity`

## Notas de desarrollo (Fase 2)

Los modelos están preparados para extensión futura:

- Inventario: añadir campo `product_template_id` en `vidrios.formula` y generar movimientos de stock.
- Factura: añadir botón "Crear factura" que genere `account.move` desde la orden.
