from datetime import timedelta
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from .models import Categoria, ConfiguracionTienda, DetalleVenta, Marca, Producto, Venta


def asegurar_ventas_demostracion():
    """
    Si existen al menos 5 productos en el catálogo y aún no hay ventas registradas,
    genera un conjunto realista de ventas históricas (hoy, esta semana, este mes y meses previos)
    para que el Dashboard y el módulo de Contabilidad muestren datos reales desde el primer uso.
    No afecta las pruebas unitarias (que crean solo 1 producto en setUp).
    """
    if Venta.objects.exists():
        return
    productos = list(Producto.objects.select_related('categoria', 'marca').order_by('id'))
    if len(productos) < 5:
        return

    ahora = timezone.now()
    config = ConfiguracionTienda.obtener()
    iva_pct = config.iva_porcentaje or 19

    # Definición de ventas semilla: (dias_atras, horas_atras, cliente, email, metodo, estado, items[(idx_prod, cant)], notas)
    semillas = [
        (0, 1, 'Camila Rojas', 'camila.rojas@email.cl', 'tarjeta', 'completada', [(0, 1), (2, 2)], 'Entrega en tienda'),
        (0, 3, 'Matías Soto', 'msoto@correo.cl', 'transferencia', 'completada', [(1, 1), (7, 1)], 'Despacho a domicilio'),
        (0, 5, 'Valentina Muñoz', 'val.munoz@email.cl', 'tarjeta', 'pendiente', [(5, 2), (8, 1)], 'Pendiente confirmación bancaria'),
        (1, 2, 'Sebastián Contreras', 'scontreras@empresa.cl', 'tarjeta', 'completada', [(0, 2)], 'Cliente frecuente'),
        (2, 4, 'Francisca Díaz', 'fdiaz@correo.cl', 'efectivo', 'completada', [(3, 2), (4, 1)], 'Consulta veterinaria'),
        (3, 6, 'Diego Morales', 'diego.morales@email.cl', 'tarjeta', 'completada', [(6, 1), (5, 1)], 'Regalo mascota'),
        (4, 3, 'Javiera Silva', 'jsilva@correo.cl', 'transferencia', 'completada', [(1, 2), (7, 2)], 'Pedido mensual'),
        (5, 5, 'Nicolás Fuentes', 'nfuentes@email.cl', 'tarjeta', 'completada', [(2, 3), (8, 2)], ''),
        (6, 2, 'Carolina Vargas', 'cvargas@correo.cl', 'tarjeta', 'cancelada', [(6, 1)], 'Anulada a solicitud del cliente'),
        (9, 4, 'Andrés Pizarro', 'apizarro@email.cl', 'transferencia', 'completada', [(0, 1), (3, 1)], ''),
        (12, 3, 'Daniela Castro', 'dcastro@correo.cl', 'tarjeta', 'completada', [(4, 2), (7, 1)], ''),
        (16, 5, 'Felipe Riquelme', 'friquelme@email.cl', 'efectivo', 'completada', [(1, 1), (2, 2), (5, 1)], ''),
        (21, 2, 'Constanza Espinoza', 'cespinoza@correo.cl', 'tarjeta', 'completada', [(0, 1), (6, 1)], ''),
        (26, 4, 'Rodrigo Araya', 'raraya@email.cl', 'transferencia', 'completada', [(3, 3), (8, 1)], ''),
        (38, 3, 'Paulina Tapia', 'ptapia@correo.cl', 'tarjeta', 'completada', [(0, 2), (5, 2)], 'Mes anterior'),
        (65, 2, 'Gonzalo Reyes', 'greyes@email.cl', 'tarjeta', 'completada', [(1, 2), (6, 1)], 'Dos meses atrás'),
    ]

    with transaction.atomic():
        for dias, horas, cliente, email, metodo, estado, items, notas in semillas:
            fecha_venta = ahora - timedelta(days=dias, hours=horas)
            venta = Venta.objects.create(
                cliente_nombre=cliente,
                cliente_email=email,
                metodo_pago=metodo,
                estado=estado,
                notas=notas,
                fecha=fecha_venta,
            )
            for prod_idx, cantidad in items:
                prod = productos[prod_idx % len(productos)]
                DetalleVenta.objects.create(
                    venta=venta,
                    producto=prod,
                    nombre_producto=prod.nombre,
                    cantidad=cantidad,
                    precio_unitario=prod.precio,
                    subtotal=prod.precio * cantidad,
                )
            venta.recalcular_totales(iva_pct=iva_pct)


def filtrar_ventas_y_totales(params):
    """
    Aplica filtros sobre Venta (fecha_desde, fecha_hasta, periodo, producto_id, estado, metodo_pago, q)
    y calcula automáticamente subtotales netos, IVA y total general.
    """
    asegurar_ventas_demostracion()
    qs = Venta.objects.prefetch_related('detalles', 'detalles__producto').select_related('usuario')

    ahora_local = timezone.localtime(timezone.now())
    hoy_inicio = ahora_local.replace(hour=0, minute=0, second=0, microsecond=0)

    periodo = (params.get('periodo') or '').strip().lower()
    fecha_desde = (params.get('fecha_desde') or '').strip()
    fecha_hasta = (params.get('fecha_hasta') or '').strip()
    producto_id = (params.get('producto') or params.get('producto_id') or '').strip()
    estado = (params.get('estado') or '').strip().lower()
    metodo_pago = (params.get('metodo_pago') or '').strip().lower()
    q = (params.get('q') or '').strip()

    if periodo == 'hoy':
        qs = qs.filter(fecha__gte=hoy_inicio)
    elif periodo == 'semana':
        inicio_semana = hoy_inicio - timedelta(days=hoy_inicio.weekday())
        qs = qs.filter(fecha__gte=inicio_semana)
    elif periodo == 'mes':
        inicio_mes = hoy_inicio.replace(day=1)
        qs = qs.filter(fecha__gte=inicio_mes)

    if fecha_desde:
        qs = qs.filter(fecha__date__gte=fecha_desde)
    if fecha_hasta:
        qs = qs.filter(fecha__date__lte=fecha_hasta)

    if producto_id and producto_id.isdigit():
        qs = qs.filter(detalles__producto_id=int(producto_id)).distinct()

    if estado in ('completada', 'pendiente', 'cancelada'):
        qs = qs.filter(estado=estado)

    if metodo_pago in ('tarjeta', 'transferencia', 'efectivo'):
        qs = qs.filter(metodo_pago=metodo_pago)

    if q:
        qs = qs.filter(
            Q(folio__icontains=q)
            | Q(cliente_nombre__icontains=q)
            | Q(cliente_email__icontains=q)
            | Q(detalles__nombre_producto__icontains=q)
        ).distinct()

    ventas_lista = list(qs.order_by('-fecha', '-id'))

    # Contabilizamos totales sobre las ventas filtradas (excluyendo canceladas a menos que se filtre explícitamente por canceladas)
    ventas_computables = (
        ventas_lista if estado == 'cancelada' else [v for v in ventas_lista if v.estado != 'cancelada']
    )
    subtotal_neto = sum(v.subtotal for v in ventas_computables)
    iva_total = sum(v.iva for v in ventas_computables)
    total_bruto = sum(v.total for v in ventas_computables)
    cantidad_computables = len(ventas_computables)
    ticket_promedio = int(round(total_bruto / cantidad_computables)) if cantidad_computables > 0 else 0

    resumen = {
        'cantidad_total': len(ventas_lista),
        'cantidad_computables': cantidad_computables,
        'subtotal_neto': subtotal_neto,
        'iva_total': iva_total,
        'total_bruto': total_bruto,
        'ticket_promedio': ticket_promedio,
    }
    return ventas_lista, resumen


def obtener_metricas_dashboard():
    """
    Calcula todas las métricas, KPIs, series de gráficos y rankings para el Dashboard Administrativo.
    """
    asegurar_ventas_demostracion()
    config = ConfiguracionTienda.obtener()
    umbral_stock = config.stock_minimo_alerta or 10

    ahora_local = timezone.localtime(timezone.now())
    hoy_inicio = ahora_local.replace(hour=0, minute=0, second=0, microsecond=0)
    inicio_semana = hoy_inicio - timedelta(days=hoy_inicio.weekday())
    inicio_mes = hoy_inicio.replace(day=1)

    ventas_completadas = Venta.objects.filter(estado='completada')
    ventas_pendientes_count = Venta.objects.filter(estado='pendiente').count()
    ventas_canceladas_count = Venta.objects.filter(estado='cancelada').count()

    agg_total = ventas_completadas.aggregate(
        monto=Sum('total'),
        neto=Sum('subtotal'),
        iva=Sum('iva'),
        cantidad=Count('id'),
    )
    total_ventas_monto = agg_total['monto'] or 0
    total_ventas_neto = agg_total['neto'] or 0
    total_ventas_iva = agg_total['iva'] or 0
    numero_ventas = agg_total['cantidad'] or 0
    ticket_promedio = int(round(total_ventas_monto / numero_ventas)) if numero_ventas > 0 else 0

    # Ventas por periodo (Hoy, Semana, Mes)
    agg_hoy = ventas_completadas.filter(fecha__gte=hoy_inicio).aggregate(monto=Sum('total'), cantidad=Count('id'))
    agg_semana = ventas_completadas.filter(fecha__gte=inicio_semana).aggregate(monto=Sum('total'), cantidad=Count('id'))
    agg_mes = ventas_completadas.filter(fecha__gte=inicio_mes).aggregate(monto=Sum('total'), cantidad=Count('id'))

    # Producto más vendido y Top 5 productos
    top_qs = (
        DetalleVenta.objects.filter(venta__estado='completada')
        .values('producto_id', 'nombre_producto')
        .annotate(
            unidades=Sum('cantidad'),
            ingresos=Sum('subtotal'),
        )
        .order_by('-unidades', '-ingresos')
    )
    top_productos = list(top_qs[:5])
    if top_productos:
        mas_vendido = top_productos[0]
    else:
        mas_vendido = {
            'producto_id': None,
            'nombre_producto': 'Sin ventas aún',
            'unidades': 0,
            'ingresos': 0,
        }

    # Métricas de catálogo e inventario
    productos_qs = Producto.objects.select_related('categoria', 'marca')
    total_productos = productos_qs.count()
    unidades_stock = productos_qs.aggregate(t=Sum('stock'))['t'] or 0
    valor_inventario = sum(p.precio * p.stock for p in productos_qs)
    bajo_stock_qs = productos_qs.filter(stock__lte=umbral_stock).order_by('stock', 'nombre')
    productos_agotados = productos_qs.filter(stock=0).count()

    # Serie últimos 7 días
    dias_nombres = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    labels_7d = []
    ingresos_7d = []
    cantidades_7d = []
    for i in range(6, -1, -1):
        dia_inicio = hoy_inicio - timedelta(days=i)
        dia_fin = dia_inicio + timedelta(days=1)
        agg_d = ventas_completadas.filter(fecha__gte=dia_inicio, fecha__lt=dia_fin).aggregate(
            m=Sum('total'), c=Count('id')
        )
        nombre_dia = dias_nombres[dia_inicio.weekday()]
        labels_7d.append(f"{nombre_dia} {dia_inicio.strftime('%d/%m')}")
        ingresos_7d.append(agg_d['m'] or 0)
        cantidades_7d.append(agg_d['c'] or 0)

    # Serie últimos 30 días (agrupado en 6 bloques de 5 días para máxima legibilidad)
    labels_30d = []
    ingresos_30d = []
    cantidades_30d = []
    for bloque in range(5, -1, -1):
        fin_bloque = hoy_inicio + timedelta(days=1) - timedelta(days=bloque * 5)
        ini_bloque = fin_bloque - timedelta(days=5)
        agg_b = ventas_completadas.filter(fecha__gte=ini_bloque, fecha__lt=fin_bloque).aggregate(
            m=Sum('total'), c=Count('id')
        )
        labels_30d.append(f"{ini_bloque.strftime('%d/%m')} - {(fin_bloque - timedelta(days=1)).strftime('%d/%m')}")
        ingresos_30d.append(agg_b['m'] or 0)
        cantidades_30d.append(agg_b['c'] or 0)

    # Serie últimos 6 meses
    meses_nombres = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    labels_6m = []
    ingresos_6m = []
    cantidades_6m = []
    for m_offset in range(5, -1, -1):
        year = hoy_inicio.year
        month = hoy_inicio.month - m_offset
        while month <= 0:
            month += 12
            year -= 1
        mes_ini = hoy_inicio.replace(year=year, month=month, day=1)
        if month == 12:
            mes_fin = mes_ini.replace(year=year + 1, month=1, day=1)
        else:
            mes_fin = mes_ini.replace(month=month + 1, day=1)
        agg_m = ventas_completadas.filter(fecha__gte=mes_ini, fecha__lt=mes_fin).aggregate(
            m=Sum('total'), c=Count('id')
        )
        labels_6m.append(f"{meses_nombres[month - 1]} {year}")
        ingresos_6m.append(agg_m['m'] or 0)
        cantidades_6m.append(agg_m['c'] or 0)

    # Ventas por categoría
    cat_ventas = (
        DetalleVenta.objects.filter(venta__estado='completada', producto__categoria__isnull=False)
        .values(cat_nombre=F('producto__categoria__nombre'))
        .annotate(ingresos=Sum('subtotal'), unidades=Sum('cantidad'))
        .order_by('-ingresos')
    )
    ventas_por_categoria = {
        'labels': [c['cat_nombre'] for c in cat_ventas] or ['Sin datos'],
        'ingresos': [c['ingresos'] or 0 for c in cat_ventas] or [0],
        'unidades': [c['unidades'] or 0 for c in cat_ventas] or [0],
    }

    ultimas_ventas = [
        v.to_dict()
        for v in Venta.objects.prefetch_related('detalles').select_related('usuario').order_by('-fecha', '-id')[:8]
    ]

    return {
        'total_ventas_monto': total_ventas_monto,
        'total_ventas_neto': total_ventas_neto,
        'total_ventas_iva': total_ventas_iva,
        'numero_ventas': numero_ventas,
        'ventas_pendientes': ventas_pendientes_count,
        'ventas_canceladas': ventas_canceladas_count,
        'ticket_promedio': ticket_promedio,
        'ventas_hoy': {
            'monto': agg_hoy['monto'] or 0,
            'cantidad': agg_hoy['cantidad'] or 0,
        },
        'ventas_semana': {
            'monto': agg_semana['monto'] or 0,
            'cantidad': agg_semana['cantidad'] or 0,
        },
        'ventas_mes': {
            'monto': agg_mes['monto'] or 0,
            'cantidad': agg_mes['cantidad'] or 0,
        },
        'producto_mas_vendido': mas_vendido,
        'top_productos': top_productos,
        'total_productos': total_productos,
        'unidades_stock': unidades_stock,
        'valor_inventario': valor_inventario,
        'productos_bajo_stock_count': bajo_stock_qs.count(),
        'productos_agotados_count': productos_agotados,
        'productos_bajo_stock': [p.to_dict() for p in bajo_stock_qs[:6]],
        'total_categorias': Categoria.objects.count(),
        'total_marcas': Marca.objects.count(),
        'total_usuarios': User.objects.count(),
        'series': {
            'dias_7': {'labels': labels_7d, 'ingresos': ingresos_7d, 'cantidades': cantidades_7d},
            'dias_30': {'labels': labels_30d, 'ingresos': ingresos_30d, 'cantidades': cantidades_30d},
            'meses_6': {'labels': labels_6m, 'ingresos': ingresos_6m, 'cantidades': cantidades_6m},
        },
        'ventas_por_categoria': ventas_por_categoria,
        'ultimas_ventas': ultimas_ventas,
    }

