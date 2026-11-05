# webapp/views.py
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from .models import Categoria, ConfiguracionTienda, DetalleVenta, Marca, Producto, Venta
from .services import obtener_metricas_dashboard


# =====================================================================
# VISTAS PÚBLICAS DE LA TIENDA
# =====================================================================
def portal_dashboard(request):
    productos = Producto.objects.select_related('categoria', 'marca')
    categorias = Categoria.objects.annotate(
        total=Count('productos'),
        stock_total=Sum('productos__stock'),
    )
    marcas = Marca.objects.annotate(total=Count('productos'))
    contexto = {
        'destacados': productos.order_by('-creado', 'id')[:6],
        'categorias': categorias,
        'marcas': marcas[:6],
        'especies': Producto.ESPECIES,
        'total_productos': productos.count(),
        'total_marcas': marcas.count(),
        'unidades_stock': Producto.objects.aggregate(t=Sum('stock'))['t'] or 0,
    }
    return render(request, 'dashboard.html', contexto)


def lista_productos(request):
    productos = Producto.objects.select_related('categoria', 'marca')
    categoria_id = (request.GET.get('categoria') or '').strip()
    marca_id = (request.GET.get('marca') or '').strip()
    especie = (request.GET.get('especie') or '').strip()
    q = (request.GET.get('q') or '').strip()
    orden = (request.GET.get('orden') or 'nombre').strip()

    if categoria_id and categoria_id.isdigit():
        productos = productos.filter(categoria_id=int(categoria_id))
    if marca_id and marca_id.isdigit():
        productos = productos.filter(marca_id=int(marca_id))
    if especie:
        productos = productos.filter(especie=especie)
    if q:
        productos = productos.filter(
            Q(nombre__icontains=q)
            | Q(descripcion__icontains=q)
            | Q(categoria__nombre__icontains=q)
            | Q(marca__nombre__icontains=q)
        )

    mapa_orden = {
        'nombre': 'nombre',
        'precio_asc': 'precio',
        'precio_desc': '-precio',
        'recientes': '-creado',
    }
    if orden not in mapa_orden:
        orden = 'nombre'
    productos = productos.order_by(mapa_orden[orden])

    # Preparamos banderas booleanas de selección para evitar operadores '==' dentro de atributos HTML
    categorias_list = list(Categoria.objects.all())
    for c in categorias_list:
        c.seleccionado = (categoria_id == str(c.id))

    marcas_list = list(Marca.objects.all())
    for m in marcas_list:
        m.seleccionado = (marca_id == str(m.id))

    especies_list = [
        {'valor': valor, 'nombre': nombre, 'seleccionado': (especie == valor)}
        for valor, nombre in Producto.ESPECIES
    ]

    ordenes_list = [
        {'valor': 'nombre', 'nombre': 'Nombre (A-Z)', 'seleccionado': (orden == 'nombre')},
        {'valor': 'precio_asc', 'nombre': 'Menor precio', 'seleccionado': (orden == 'precio_asc')},
        {'valor': 'precio_desc', 'nombre': 'Mayor precio', 'seleccionado': (orden == 'precio_desc')},
        {'valor': 'recientes', 'nombre': 'Más recientes', 'seleccionado': (orden == 'recientes')},
    ]

    hay_filtros = bool(categoria_id or marca_id or especie or q or orden != 'nombre')

    contexto = {
        'productos': productos,
        'total_resultados': productos.count(),
        'categorias': categorias_list,
        'marcas': marcas_list,
        'especies': Producto.ESPECIES,
        'especies_opciones': especies_list,
        'ordenes_opciones': ordenes_list,
        'categoria_sel': categoria_id,
        'marca_sel': marca_id,
        'especie_sel': especie,
        'q_sel': q,
        'orden_sel': orden,
        'hay_filtros': hay_filtros,
    }
    return render(request, 'productos.html', contexto)


def detalle_producto(request, pk):
    producto = get_object_or_404(Producto.objects.select_related('categoria', 'marca'), pk=pk)
    relacionados = (
        Producto.objects.select_related('categoria', 'marca')
        .filter(Q(categoria=producto.categoria) | Q(especie=producto.especie))
        .exclude(pk=producto.pk)
        .distinct()[:3]
    )
    return render(request, 'detalle.html', {
        'producto': producto,
        'relacionados': relacionados,
    })


def comprar_producto(request):
    """Permite registrar un pedido desde la tienda pública descontando stock automáticamente."""
    if request.method != 'POST':
        return redirect('lista_productos')

    producto_id = request.POST.get('producto_id')
    producto = get_object_or_404(Producto, pk=producto_id)

    try:
        cantidad = int(request.POST.get('cantidad', 1))
    except (ValueError, TypeError):
        cantidad = 1

    if cantidad <= 0:
        messages.error(request, 'La cantidad seleccionada debe ser mayor a 0.')
        return redirect('detalle_producto', pk=producto.pk)

    cliente_nombre = (request.POST.get('cliente_nombre') or '').strip()
    cliente_email = (request.POST.get('cliente_email') or '').strip()
    metodo_pago = (request.POST.get('metodo_pago') or 'tarjeta').strip()

    if not cliente_nombre:
        if request.user.is_authenticated:
            cliente_nombre = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
        else:
            cliente_nombre = 'Cliente Web'

    if not cliente_email and request.user.is_authenticated:
        cliente_email = request.user.email or ''

    if metodo_pago not in ('tarjeta', 'transferencia', 'efectivo'):
        metodo_pago = 'tarjeta'

    config = ConfiguracionTienda.obtener()
    iva_pct = config.iva_porcentaje or 19

    with transaction.atomic():
        prod_lock = Producto.objects.select_for_update().get(pk=producto.pk)
        if prod_lock.stock < cantidad:
            messages.error(
                request,
                f"Stock insuficiente para '{prod_lock.nombre}'. Disponibles: {prod_lock.stock} unidades."
            )
            return redirect('detalle_producto', pk=producto.pk)

        venta = Venta.objects.create(
            cliente_nombre=cliente_nombre,
            cliente_email=cliente_email,
            usuario=request.user if request.user.is_authenticated else None,
            estado='completada',
            metodo_pago=metodo_pago,
            notas='Compra realizada en tienda online',
        )
        DetalleVenta.objects.create(
            venta=venta,
            producto=prod_lock,
            nombre_producto=prod_lock.nombre,
            cantidad=cantidad,
            precio_unitario=prod_lock.precio,
            subtotal=prod_lock.precio * cantidad,
        )
        prod_lock.stock -= cantidad
        prod_lock.save(update_fields=['stock'])
        venta.recalcular_totales(iva_pct=iva_pct)

    messages.success(
        request,
        f"¡Compra registrada con éxito! Folio {venta.folio} por ${venta.total:,} CLP ({cantidad}x {producto.nombre}).".replace(',', '.')
    )
    return redirect('detalle_producto', pk=producto.pk)


def lista_categorias(request):
    categorias = Categoria.objects.annotate(
        total=Count('productos'),
        stock_total=Sum('productos__stock'),
    )
    return render(request, 'categorias.html', {'categorias': categorias})


def lista_marcas(request):
    marcas = Marca.objects.annotate(
        total=Count('productos'),
        stock_total=Sum('productos__stock'),
    )
    return render(request, 'marcas.html', {'marcas': marcas})


def api_docs(request):
    """Vista informativa pública del catálogo."""
    return render(request, 'api_docs.html')


@login_required(login_url='login')
def api_docs_admin(request):
    """Vista protegida restringida exclusivamente a superusuarios."""
    if not request.user.is_superuser:
        messages.error(request, 'Acceso denegado: se requieren permisos de superusuario.')
        return redirect('api_docs')
    return render(request, 'api_docs_admin.html')


# =====================================================================
# AUTENTICACIÓN Y PANEL DE ADMINISTRACIÓN INTEGRAL
# =====================================================================
def login_view(request):
    """Vista de inicio de sesión con redirección inteligente."""
    if request.user.is_authenticated:
        siguiente = request.GET.get('next') or request.POST.get('next') or 'portal_home'
        return redirect(siguiente)

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            usuario = form.get_user()
            login(request, usuario)
            messages.success(request, f'¡Bienvenido(a) de vuelta, {usuario.username}!')
            siguiente = request.POST.get('next')
            if not siguiente:
                siguiente = 'admin_api' if usuario.is_superuser else 'portal_home'
            return redirect(siguiente)
        else:
            messages.error(request, 'Usuario o contraseña incorrectos. Por favor, verifica tus credenciales.')
    else:
        form = AuthenticationForm()

    return render(request, 'login.html', {
        'form': form,
        'next': request.GET.get('next', '')
    })


def logout_view(request):
    """Cierra la sesión del usuario y redirige a la página principal."""
    logout(request)
    messages.info(request, 'Has cerrado sesión correctamente.')
    return redirect('portal_home')


@login_required(login_url='login')
def admin_api_test(request):
    """
    Panel de Administración Integral de Patitas Chile.
    Restringido exclusivamente a superusuarios. Gestiona Dashboard, Contabilidad de Ventas,
    Catálogo (Productos, Categorías, Marcas), Usuarios y Configuración directamente desde la interfaz.
    """
    if not request.user.is_superuser:
        messages.error(request, 'Acceso denegado: se requieren permisos de administrador para acceder al panel de gestión.')
        return redirect('portal_home')

    metricas = obtener_metricas_dashboard()
    categorias = Categoria.objects.annotate(total_productos=Count('productos')).order_by('nombre')
    marcas = Marca.objects.annotate(total_productos=Count('productos')).order_by('nombre')
    productos = Producto.objects.select_related('categoria', 'marca').order_by('nombre')
    seccion_activa = request.GET.get('seccion', 'dashboard')

    return render(request, 'admin_api.html', {
        'metricas': metricas,
        'categorias': categorias,
        'marcas': marcas,
        'productos_catalogo': productos,
        'especies': Producto.ESPECIES,
        'seccion_activa': seccion_activa,
    })
