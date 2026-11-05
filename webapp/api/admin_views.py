# webapp/api/admin_views.py
import csv
import json
import logging
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from webapp.models import Categoria, ConfiguracionTienda, DetalleVenta, Marca, Producto, Venta
from webapp.services import filtrar_ventas_y_totales, obtener_metricas_dashboard

logger = logging.getLogger('admin_api')

CAMPOS_PRODUCTO = ['nombre', 'descripcion', 'precio', 'stock', 'especie']


def parse_json(request):
    """Parsea el cuerpo de la petición como JSON y valida formato."""
    try:
        data = json.loads(request.body or '{}')
        if not isinstance(data, dict):
            return None, JsonResponse({
                'error': 'Petición inválida.',
                'detalle': 'El cuerpo de la petición debe ser un objeto JSON válido.'
            }, status=400)
        return data, None
    except (ValueError, json.JSONDecodeError) as e:
        return None, JsonResponse({
            'error': 'JSON malformado.',
            'detalle': str(e)
        }, status=400)


def log_audit(request, action, resource_name, resource_id=None, extra=None):
    """Registra en logs las operaciones de escritura realizadas por superusuarios."""
    user = request.user
    logger.info(
        f"[AUDIT ADMIN_API] Superusuario='{user.username}' (ID={user.id}) | "
        f"Acción={action} | Recurso='{resource_name}' (ID={resource_id or 'N/A'}) | "
        f"Ruta={request.path} | IP={request.META.get('REMOTE_ADDR', 'N/A')} | Info={extra or {}}"
    )


def resolve_producto_relations(producto, data):
    """Asigna y valida claves foráneas categoria_id y marca_id."""
    if 'categoria_id' in data:
        try:
            producto.categoria = Categoria.objects.get(pk=data['categoria_id'])
        except (Categoria.DoesNotExist, ValueError, TypeError):
            return JsonResponse({
                'error': 'Validación fallida.',
                'detalle': f"La categoría con ID {data.get('categoria_id')} no existe."
            }, status=400)

    if 'marca_id' in data:
        marca_id = data['marca_id']
        if marca_id in (None, ''):
            producto.marca = None
        else:
            try:
                producto.marca = Marca.objects.get(pk=marca_id)
            except (Marca.DoesNotExist, ValueError, TypeError):
                return JsonResponse({
                    'error': 'Validación fallida.',
                    'detalle': f"La marca con ID {marca_id} no existe."
                }, status=400)
    return None


def save_model_instance(instance):
    """Ejecuta validaciones del modelo (full_clean) y persiste en base de datos."""
    try:
        instance.full_clean()
        instance.save()
        return None
    except ValidationError as err:
        return JsonResponse({
            'error': 'Error de validación en los campos del modelo.',
            'detalle': err.message_dict
        }, status=400)


# =====================================================================
# ENDPOINTS DE ADMINISTRACIÓN: PRODUCTOS
# =====================================================================
def admin_productos_collection(request):
    """
    Admin API - Productos Colección:
      - GET: Listado administrativo completo con búsqueda, filtros y ordenamiento.
      - POST: Creación de nuevo producto (Código 201).
    """
    if request.method == 'GET':
        qs = Producto.objects.select_related('categoria', 'marca')
        categoria = request.GET.get('categoria')
        marca = request.GET.get('marca')
        especie = request.GET.get('especie')
        stock_estado = request.GET.get('stock_estado')
        q = (request.GET.get('q') or '').strip()
        orden = request.GET.get('orden', 'nombre')

        if categoria:
            qs = qs.filter(categoria_id=categoria)
        if marca:
            qs = qs.filter(marca_id=marca)
        if especie:
            qs = qs.filter(especie=especie)
        if stock_estado == 'agotado':
            qs = qs.filter(stock=0)
        elif stock_estado == 'bajo':
            umbral = ConfiguracionTienda.obtener().stock_minimo_alerta
            qs = qs.filter(stock__gt=0, stock__lte=umbral)
        elif stock_estado == 'disponible':
            qs = qs.filter(stock__gt=0)

        if q:
            qs = qs.filter(
                Q(nombre__icontains=q)
                | Q(descripcion__icontains=q)
                | Q(categoria__nombre__icontains=q)
                | Q(marca__nombre__icontains=q)
            )

        ordenes_validos = {
            'nombre': 'nombre',
            '-nombre': '-nombre',
            'precio_asc': 'precio',
            'precio_desc': '-precio',
            'stock_asc': 'stock',
            'stock_desc': '-stock',
            'recientes': '-creado',
            'id': 'id',
            '-id': '-id',
        }
        qs = qs.order_by(ordenes_validos.get(orden, 'nombre'))

        return JsonResponse({
            'count': qs.count(),
            'results': [p.to_dict() for p in qs]
        }, status=200)

    if request.method == 'POST':
        data, err = parse_json(request)
        if err:
            return err

        # Validaciones de campos obligatorios para creación
        required = ['nombre', 'precio', 'categoria_id']
        missing = [f for f in required if f not in data or data[f] in (None, '')]
        if missing:
            return JsonResponse({
                'error': 'Faltan campos obligatorios para la creación del producto.',
                'campos_faltantes': missing
            }, status=400)

        producto = Producto()
        for field in CAMPOS_PRODUCTO:
            if field in data:
                setattr(producto, field, data[field])

        rel_err = resolve_producto_relations(producto, data)
        if rel_err:
            return rel_err

        save_err = save_model_instance(producto)
        if save_err:
            return save_err

        log_audit(request, 'POST_CREATE', 'Producto', producto.id, {'nombre': producto.nombre, 'precio': producto.precio})
        return JsonResponse(producto.to_dict(), status=201)

    return JsonResponse({'error': 'Método no permitido.', 'permitidos': ['GET', 'POST']}, status=405)


def admin_producto_detail(request, pk):
    """
    Admin API - Producto Detalle:
      - GET: Obtener detalle del recurso (Código 200).
      - PUT: Actualización completa requerida (Código 200).
      - PATCH: Actualización parcial (Código 200).
      - DELETE: Eliminación del recurso (Código 204 No Content).
    """
    try:
        producto = Producto.objects.select_related('categoria', 'marca').get(pk=pk)
    except Producto.DoesNotExist:
        return JsonResponse({'error': 'Recurso no encontrado.', 'detalle': f'Producto con id {pk} no existe.'}, status=404)

    if request.method == 'GET':
        return JsonResponse(producto.to_dict(), status=200)

    if request.method in ('PUT', 'PATCH'):
        data, err = parse_json(request)
        if err:
            return err

        if request.method == 'PUT':
            mandatorios = ['nombre', 'precio', 'stock', 'categoria_id']
            faltantes = [c for c in mandatorios if c not in data]
            if faltantes:
                return JsonResponse({
                    'error': 'PUT requiere actualización completa del recurso.',
                    'campos_requeridos': faltantes
                }, status=400)

        for field in CAMPOS_PRODUCTO:
            if field in data:
                setattr(producto, field, data[field])

        rel_err = resolve_producto_relations(producto, data)
        if rel_err:
            return rel_err

        save_err = save_model_instance(producto)
        if save_err:
            return save_err

        log_audit(request, request.method, 'Producto', producto.id, {'nombre': producto.nombre})
        return JsonResponse(producto.to_dict(), status=200)

    if request.method == 'DELETE':
        prod_id = producto.id
        prod_nombre = producto.nombre
        producto.delete()
        log_audit(request, 'DELETE', 'Producto', prod_id, {'nombre': prod_nombre})
        return HttpResponse(status=204)

    return JsonResponse({'error': 'Método no permitido.', 'permitidos': ['GET', 'PUT', 'PATCH', 'DELETE']}, status=405)


# =====================================================================
# ENDPOINTS DE ADMINISTRACIÓN: CATEGORÍAS
# =====================================================================
def admin_categorias_collection(request):
    """Admin API - Categorías Colección (GET, POST)."""
    if request.method == 'GET':
        qs = Categoria.objects.annotate(total_productos=Count('productos')).order_by('nombre')
        results = [c.to_dict() for c in qs]
        return JsonResponse({'count': len(results), 'results': results}, status=200)

    if request.method == 'POST':
        data, err = parse_json(request)
        if err:
            return err

        if 'nombre' not in data or not str(data['nombre']).strip():
            return JsonResponse({'error': 'El campo nombre es obligatorio.'}, status=400)

        categoria = Categoria(nombre=str(data['nombre']).strip(), descripcion=str(data.get('descripcion', '')).strip())
        save_err = save_model_instance(categoria)
        if save_err:
            return save_err

        log_audit(request, 'POST_CREATE', 'Categoria', categoria.id, {'nombre': categoria.nombre})
        return JsonResponse(categoria.to_dict(), status=201)

    return JsonResponse({'error': 'Método no permitido.', 'permitidos': ['GET', 'POST']}, status=405)


def admin_categoria_detail(request, pk):
    """Admin API - Categoría Detalle (GET, PUT, PATCH, DELETE)."""
    try:
        categoria = Categoria.objects.annotate(total_productos=Count('productos')).get(pk=pk)
    except Categoria.DoesNotExist:
        return JsonResponse({'error': 'Categoría no encontrada.'}, status=404)

    if request.method == 'GET':
        return JsonResponse(categoria.to_dict(), status=200)

    if request.method in ('PUT', 'PATCH'):
        data, err = parse_json(request)
        if err:
            return err
        if 'nombre' in data:
            categoria.nombre = str(data['nombre']).strip()
        if 'descripcion' in data:
            categoria.descripcion = str(data['descripcion']).strip()
        save_err = save_model_instance(categoria)
        if save_err:
            return save_err

        log_audit(request, request.method, 'Categoria', categoria.id)
        return JsonResponse(categoria.to_dict(), status=200)

    if request.method == 'DELETE':
        cat_id = categoria.id
        categoria.delete()
        log_audit(request, 'DELETE', 'Categoria', cat_id)
        return HttpResponse(status=204)

    return JsonResponse({'error': 'Método no permitido.', 'permitidos': ['GET', 'PUT', 'PATCH', 'DELETE']}, status=405)


# =====================================================================
# ENDPOINTS DE ADMINISTRACIÓN: MARCAS
# =====================================================================
def admin_marcas_collection(request):
    """Admin API - Marcas Colección (GET, POST)."""
    if request.method == 'GET':
        qs = Marca.objects.annotate(total_productos=Count('productos')).order_by('nombre')
        results = [m.to_dict() for m in qs]
        return JsonResponse({'count': len(results), 'results': results}, status=200)

    if request.method == 'POST':
        data, err = parse_json(request)
        if err:
            return err

        if 'nombre' not in data or not str(data['nombre']).strip():
            return JsonResponse({'error': 'El campo nombre es obligatorio.'}, status=400)

        marca = Marca(nombre=str(data['nombre']).strip(), pais_origen=str(data.get('pais_origen', '')).strip())
        save_err = save_model_instance(marca)
        if save_err:
            return save_err

        log_audit(request, 'POST_CREATE', 'Marca', marca.id, {'nombre': marca.nombre})
        return JsonResponse(marca.to_dict(), status=201)

    return JsonResponse({'error': 'Método no permitido.', 'permitidos': ['GET', 'POST']}, status=405)


def admin_marca_detail(request, pk):
    """Admin API - Marca Detalle (GET, PUT, PATCH, DELETE)."""
    try:
        marca = Marca.objects.annotate(total_productos=Count('productos')).get(pk=pk)
    except Marca.DoesNotExist:
        return JsonResponse({'error': 'Marca no encontrada.'}, status=404)

    if request.method == 'GET':
        return JsonResponse(marca.to_dict(), status=200)

    if request.method in ('PUT', 'PATCH'):
        data, err = parse_json(request)
        if err:
            return err
        if 'nombre' in data:
            marca.nombre = str(data['nombre']).strip()
        if 'pais_origen' in data:
            marca.pais_origen = str(data['pais_origen']).strip()
        save_err = save_model_instance(marca)
        if save_err:
            return save_err

        log_audit(request, request.method, 'Marca', marca.id)
        return JsonResponse(marca.to_dict(), status=200)

    if request.method == 'DELETE':
        m_id = marca.id
        marca.delete()
        log_audit(request, 'DELETE', 'Marca', m_id)
        return HttpResponse(status=204)

    return JsonResponse({'error': 'Método no permitido.', 'permitidos': ['GET', 'PUT', 'PATCH', 'DELETE']}, status=405)


# =====================================================================
# ENDPOINTS DE ADMINISTRACIÓN: DASHBOARD MÉTRICAS Y GRÁFICOS
# =====================================================================
def admin_metricas_dashboard(request):
    """Admin API - Obtiene KPIs, series de gráficos y resumen para el Dashboard."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Método no permitido.', 'permitidos': ['GET']}, status=405)
    metricas = obtener_metricas_dashboard()
    return JsonResponse(metricas, status=200)


# =====================================================================
# ENDPOINTS DE ADMINISTRACIÓN: VENTAS Y CONTABILIDAD
# =====================================================================
def admin_ventas_collection(request):
    """
    Admin API - Contabilidad y Registro de Ventas:
      - GET: Listado de ventas con filtros por fecha, producto, estado y cálculo de totales/subtotales.
      - POST: Registrar nueva venta con validación y descuento automático de stock.
    """
    if request.method == 'GET':
        ventas_lista, resumen = filtrar_ventas_y_totales(request.GET)
        return JsonResponse({
            'count': len(ventas_lista),
            'resumen': resumen,
            'results': [v.to_dict() for v in ventas_lista]
        }, status=200)

    if request.method == 'POST':
        data, err = parse_json(request)
        if err:
            return err

        items = data.get('items', [])
        if not isinstance(items, list) or len(items) == 0:
            return JsonResponse({
                'error': 'Debe incluir al menos un producto en la venta.',
                'detalle': 'El campo items debe ser una lista no vacía.'
            }, status=400)

        cliente_nombre = str(data.get('cliente_nombre') or 'Cliente General').strip()
        cliente_email = str(data.get('cliente_email') or '').strip()
        estado = str(data.get('estado') or 'completada').strip().lower()
        metodo_pago = str(data.get('metodo_pago') or 'tarjeta').strip().lower()
        notas = str(data.get('notas') or '').strip()

        if estado not in ('completada', 'pendiente', 'cancelada'):
            return JsonResponse({'error': 'Estado de venta inválido.'}, status=400)
        if metodo_pago not in ('tarjeta', 'transferencia', 'efectivo'):
            return JsonResponse({'error': 'Método de pago inválido.'}, status=400)

        config = ConfiguracionTienda.obtener()
        iva_pct = config.iva_porcentaje or 19

        with transaction.atomic():
            lineas_validadas = []
            for idx, item in enumerate(items, start=1):
                prod_id = item.get('producto_id')
                try:
                    cantidad = int(item.get('cantidad', 1))
                except (ValueError, TypeError):
                    return JsonResponse({'error': f'Cantidad inválida en la línea {idx}.'}, status=400)

                if cantidad <= 0:
                    return JsonResponse({'error': f'La cantidad en la línea {idx} debe ser mayor a 0.'}, status=400)

                try:
                    producto = Producto.objects.select_for_update().get(pk=prod_id)
                except (Producto.DoesNotExist, ValueError, TypeError):
                    return JsonResponse({'error': f'El producto seleccionado en la línea {idx} no existe.'}, status=400)

                if estado == 'completada' and producto.stock < cantidad:
                    return JsonResponse({
                        'error': 'Stock insuficiente.',
                        'detalle': f"'{producto.nombre}' solo tiene {producto.stock} unidades disponibles (solicitadas: {cantidad})."
                    }, status=400)

                lineas_validadas.append((producto, cantidad))

            venta = Venta.objects.create(
                cliente_nombre=cliente_nombre,
                cliente_email=cliente_email,
                usuario=request.user if request.user.is_authenticated else None,
                estado=estado,
                metodo_pago=metodo_pago,
                notas=notas,
            )

            for producto, cantidad in lineas_validadas:
                DetalleVenta.objects.create(
                    venta=venta,
                    producto=producto,
                    nombre_producto=producto.nombre,
                    cantidad=cantidad,
                    precio_unitario=producto.precio,
                    subtotal=producto.precio * cantidad,
                )
                if estado == 'completada':
                    producto.stock = max(0, producto.stock - cantidad)
                    producto.save(update_fields=['stock'])

            venta.recalcular_totales(iva_pct=iva_pct)

        log_audit(request, 'POST_CREATE', 'Venta', venta.id, {'folio': venta.folio, 'total': venta.total})
        return JsonResponse(venta.to_dict(), status=201)

    return JsonResponse({'error': 'Método no permitido.', 'permitidos': ['GET', 'POST']}, status=405)


def admin_venta_detail(request, pk):
    """
    Admin API - Detalle, cambio de estado y eliminación de Venta.
    """
    try:
        venta = Venta.objects.prefetch_related('detalles', 'detalles__producto').get(pk=pk)
    except Venta.DoesNotExist:
        return JsonResponse({'error': 'Venta no encontrada.'}, status=404)

    if request.method == 'GET':
        return JsonResponse(venta.to_dict(), status=200)

    if request.method in ('PUT', 'PATCH'):
        data, err = parse_json(request)
        if err:
            return err

        estado_anterior = venta.estado
        nuevo_estado = str(data.get('estado', venta.estado)).strip().lower()
        if nuevo_estado not in ('completada', 'pendiente', 'cancelada'):
            return JsonResponse({'error': 'Estado inválido.'}, status=400)

        with transaction.atomic():
            # Si pasa a completada desde otro estado, descontar stock
            if estado_anterior != 'completada' and nuevo_estado == 'completada':
                for det in venta.detalles.select_related('producto').all():
                    if det.producto:
                        if det.producto.stock < det.cantidad:
                            return JsonResponse({
                                'error': 'Stock insuficiente para completar la venta.',
                                'detalle': f"'{det.producto.nombre}' tiene {det.producto.stock} en stock."
                            }, status=400)
                for det in venta.detalles.select_related('producto').all():
                    if det.producto:
                        det.producto.stock = max(0, det.producto.stock - det.cantidad)
                        det.producto.save(update_fields=['stock'])

            # Si estaba completada y pasa a cancelada/pendiente, restituir stock
            elif estado_anterior == 'completada' and nuevo_estado != 'completada':
                for det in venta.detalles.select_related('producto').all():
                    if det.producto:
                        det.producto.stock += det.cantidad
                        det.producto.save(update_fields=['stock'])

            venta.estado = nuevo_estado
            if 'cliente_nombre' in data and str(data['cliente_nombre']).strip():
                venta.cliente_nombre = str(data['cliente_nombre']).strip()
            if 'cliente_email' in data:
                venta.cliente_email = str(data['cliente_email']).strip()
            if 'metodo_pago' in data and data['metodo_pago'] in ('tarjeta', 'transferencia', 'efectivo'):
                venta.metodo_pago = data['metodo_pago']
            if 'notas' in data:
                venta.notas = str(data['notas']).strip()
            venta.save()

        log_audit(request, request.method, 'Venta', venta.id, {'folio': venta.folio, 'estado': venta.estado})
        return JsonResponse(venta.to_dict(), status=200)

    if request.method == 'DELETE':
        with transaction.atomic():
            if venta.estado == 'completada':
                for det in venta.detalles.select_related('producto').all():
                    if det.producto:
                        det.producto.stock += det.cantidad
                        det.producto.save(update_fields=['stock'])
            folio = venta.folio
            v_id = venta.id
            venta.delete()
        log_audit(request, 'DELETE', 'Venta', v_id, {'folio': folio})
        return HttpResponse(status=204)

    return JsonResponse({'error': 'Método no permitido.', 'permitidos': ['GET', 'PUT', 'PATCH', 'DELETE']}, status=405)


def admin_ventas_export_csv(request):
    """
    Exporta el listado contable de ventas filtrado a un archivo CSV compatible con Excel (UTF-8 con BOM).
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Método no permitido.', 'permitidos': ['GET']}, status=405)

    ventas_lista, resumen = filtrar_ventas_y_totales(request.GET)

    fecha_str = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="contabilidad_ventas_{fecha_str}.csv"'
    # BOM UTF-8 para que Microsoft Excel reconozca tildes y caracteres especiales automáticamente
    response.write('\ufeff')

    writer = csv.writer(response, delimiter=';')
    writer.writerow([
        'Folio',
        'Fecha y Hora',
        'Cliente',
        'Correo Cliente',
        'Detalle de Productos',
        'Cantidad Ítems',
        'Método de Pago',
        'Estado',
        'Subtotal Neto (CLP)',
        'IVA 19% (CLP)',
        'Total Bruto (CLP)',
        'Notas',
    ])

    for v in ventas_lista:
        v_dict = v.to_dict()
        writer.writerow([
            v_dict['folio'],
            v_dict['fecha_formateada'],
            v_dict['cliente_nombre'],
            v_dict['cliente_email'] or '-',
            v_dict['resumen_productos'],
            v_dict['cantidad_items'],
            v_dict['metodo_pago_display'],
            v_dict['estado_display'],
            v_dict['subtotal'],
            v_dict['iva'],
            v_dict['total'],
            v_dict['notas'] or '',
        ])

    writer.writerow([])
    writer.writerow([
        'TOTALES CONTABLES (Ventas Válidas)',
        '',
        '',
        '',
        f"{resumen['cantidad_computables']} ventas computables",
        '',
        '',
        '',
        resumen['subtotal_neto'],
        resumen['iva_total'],
        resumen['total_bruto'],
        f"Ticket Promedio: ${resumen['ticket_promedio']}",
    ])

    log_audit(request, 'EXPORT_CSV', 'Venta', None, {'registros': len(ventas_lista)})
    return response


# =====================================================================
# ENDPOINTS DE ADMINISTRACIÓN: USUARIOS Y CLIENTES
# =====================================================================
def user_to_dict(u):
    if u.is_superuser:
        rol = 'superuser'
        rol_display = 'Superusuario / Admin'
    elif u.is_staff:
        rol = 'staff'
        rol_display = 'Staff / Operador'
    else:
        rol = 'cliente'
        rol_display = 'Cliente'

    return {
        'id': u.id,
        'username': u.username,
        'email': u.email or '',
        'first_name': u.first_name or '',
        'last_name': u.last_name or '',
        'nombre_completo': f"{u.first_name} {u.last_name}".strip() or u.username,
        'rol': rol,
        'rol_display': rol_display,
        'is_superuser': u.is_superuser,
        'is_staff': u.is_staff,
        'is_active': u.is_active,
        'date_joined': timezone.localtime(u.date_joined).strftime('%d/%m/%Y'),
        'total_compras': getattr(u, 'total_compras', 0),
    }


def admin_usuarios_collection(request):
    """Admin API - Gestión de Usuarios / Clientes (GET, POST)."""
    if request.method == 'GET':
        qs = User.objects.annotate(total_compras=Count('ventas')).order_by('-is_superuser', '-is_staff', 'username')
        q = (request.GET.get('q') or '').strip()
        rol = (request.GET.get('rol') or '').strip()
        if q:
            qs = qs.filter(
                Q(username__icontains=q)
                | Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )
        if rol == 'superuser':
            qs = qs.filter(is_superuser=True)
        elif rol == 'staff':
            qs = qs.filter(is_staff=True, is_superuser=False)
        elif rol == 'cliente':
            qs = qs.filter(is_staff=False, is_superuser=False)

        results = [user_to_dict(u) for u in qs]
        return JsonResponse({'count': len(results), 'results': results}, status=200)

    if request.method == 'POST':
        data, err = parse_json(request)
        if err:
            return err

        username = str(data.get('username') or '').strip()
        password = str(data.get('password') or '').strip()
        email = str(data.get('email') or '').strip()
        first_name = str(data.get('first_name') or '').strip()
        last_name = str(data.get('last_name') or '').strip()
        rol = str(data.get('rol') or 'cliente').strip()
        is_active = bool(data.get('is_active', True))

        if not username:
            return JsonResponse({'error': 'El nombre de usuario es obligatorio.'}, status=400)
        if len(password) < 6:
            return JsonResponse({'error': 'La contraseña debe tener al menos 6 caracteres.'}, status=400)
        if User.objects.filter(username__iexact=username).exists():
            return JsonResponse({'error': f"El usuario '{username}' ya existe."}, status=400)

        u = User(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            is_active=is_active,
            is_superuser=(rol == 'superuser'),
            is_staff=(rol in ('superuser', 'staff')),
        )
        u.set_password(password)
        u.save()

        log_audit(request, 'POST_CREATE', 'User', u.id, {'username': u.username, 'rol': rol})
        return JsonResponse(user_to_dict(u), status=201)

    return JsonResponse({'error': 'Método no permitido.', 'permitidos': ['GET', 'POST']}, status=405)


def admin_usuario_detail(request, pk):
    """Admin API - Detalle, Edición y Eliminación de Usuario."""
    try:
        u = User.objects.annotate(total_compras=Count('ventas')).get(pk=pk)
    except User.DoesNotExist:
        return JsonResponse({'error': 'Usuario no encontrado.'}, status=404)

    if request.method == 'GET':
        return JsonResponse(user_to_dict(u), status=200)

    if request.method in ('PUT', 'PATCH'):
        data, err = parse_json(request)
        if err:
            return err

        if 'username' in data and str(data['username']).strip():
            nuevo_username = str(data['username']).strip()
            if User.objects.filter(username__iexact=nuevo_username).exclude(pk=u.id).exists():
                return JsonResponse({'error': f"El nombre de usuario '{nuevo_username}' ya está en uso."}, status=400)
            u.username = nuevo_username

        if 'email' in data:
            u.email = str(data['email']).strip()
        if 'first_name' in data:
            u.first_name = str(data['first_name']).strip()
        if 'last_name' in data:
            u.last_name = str(data['last_name']).strip()

        if 'rol' in data:
            rol = data['rol']
            if u.id == request.user.id and rol != 'superuser':
                return JsonResponse({'error': 'No puedes quitarte el rol de superusuario a ti mismo.'}, status=400)
            u.is_superuser = (rol == 'superuser')
            u.is_staff = (rol in ('superuser', 'staff'))

        if 'is_active' in data:
            if u.id == request.user.id and not bool(data['is_active']):
                return JsonResponse({'error': 'No puedes desactivar tu propia cuenta activa.'}, status=400)
            u.is_active = bool(data['is_active'])

        if data.get('password'):
            pwd = str(data['password']).strip()
            if len(pwd) < 6:
                return JsonResponse({'error': 'La nueva contraseña debe tener al menos 6 caracteres.'}, status=400)
            u.set_password(pwd)

        u.save()
        log_audit(request, request.method, 'User', u.id, {'username': u.username})
        return JsonResponse(user_to_dict(u), status=200)

    if request.method == 'DELETE':
        if u.id == request.user.id:
            return JsonResponse({'error': 'No puedes eliminar tu propia cuenta de superusuario activa.'}, status=400)
        u_id = u.id
        u_name = u.username
        u.delete()
        log_audit(request, 'DELETE', 'User', u_id, {'username': u_name})
        return HttpResponse(status=204)

    return JsonResponse({'error': 'Método no permitido.', 'permitidos': ['GET', 'PUT', 'PATCH', 'DELETE']}, status=405)


# =====================================================================
# ENDPOINTS DE ADMINISTRACIÓN: CONFIGURACIÓN DE LA TIENDA
# =====================================================================
def admin_configuracion_view(request):
    """Admin API - Consulta y actualización de la configuración general de la tienda."""
    config = ConfiguracionTienda.obtener()
    if request.method == 'GET':
        return JsonResponse(config.to_dict(), status=200)

    if request.method in ('PUT', 'PATCH', 'POST'):
        data, err = parse_json(request)
        if err:
            return err

        campos_texto = ['nombre_tienda', 'slogan', 'email_contacto', 'telefono_contacto', 'direccion', 'horario_atencion']
        for campo in campos_texto:
            if campo in data and str(data[campo]).strip():
                setattr(config, campo, str(data[campo]).strip())

        campos_num = ['iva_porcentaje', 'stock_minimo_alerta', 'envio_gratis_desde']
        for campo in campos_num:
            if campo in data:
                try:
                    valor = int(data[campo])
                    if valor < 0:
                        raise ValueError
                    setattr(config, campo, valor)
                except (ValueError, TypeError):
                    return JsonResponse({'error': f'El campo {campo} debe ser un número entero positivo.'}, status=400)

        save_err = save_model_instance(config)
        if save_err:
            return save_err

        log_audit(request, request.method, 'ConfiguracionTienda', config.id)
        return JsonResponse(config.to_dict(), status=200)

    return JsonResponse({'error': 'Método no permitido.', 'permitidos': ['GET', 'PUT', 'PATCH']}, status=405)
