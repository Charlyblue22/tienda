# webapp/api/public_views.py
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from webapp.models import Producto, Categoria, Marca


def metodo_no_permitido_publico(permitidos):
    return JsonResponse({
        'error': 'Método no permitido en la API Base pública.',
        'permitidos': permitidos,
        'mensaje': 'Las operaciones de administración (crear, modificar, eliminar) deben realizarse en la Admin API (/api/admin/).'
    }, status=405)


@csrf_exempt
def productos_collection_public(request):
    """API Base: Consulta pública de productos (Solo GET)."""
    if request.method == 'GET':
        productos = Producto.objects.select_related('categoria', 'marca')
        categoria = request.GET.get('categoria')
        especie = request.GET.get('especie')
        if categoria:
            productos = productos.filter(categoria_id=categoria)
        if especie:
            productos = productos.filter(especie=especie)

        return JsonResponse({
            'count': productos.count(),
            'results': [p.to_dict() for p in productos]
        }, status=200)

    return metodo_no_permitido_publico(['GET'])


@csrf_exempt
def producto_detail_public(request, pk):
    """API Base: Detalle público de un producto (Solo GET)."""
    try:
        producto = Producto.objects.select_related('categoria', 'marca').get(pk=pk)
    except Producto.DoesNotExist:
        return JsonResponse({'error': 'Producto no encontrado.'}, status=404)

    if request.method == 'GET':
        return JsonResponse(producto.to_dict(), status=200)

    return metodo_no_permitido_publico(['GET'])


@csrf_exempt
def categorias_collection_public(request):
    """API Base: Consulta pública de categorías (Solo GET)."""
    if request.method == 'GET':
        results = [{'id': c.id, 'nombre': c.nombre, 'descripcion': c.descripcion} for c in Categoria.objects.all()]
        return JsonResponse({'results': results}, status=200)
    return metodo_no_permitido_publico(['GET'])


@csrf_exempt
def categoria_detail_public(request, pk):
    """API Base: Detalle público de una categoría (Solo GET)."""
    try:
        c = Categoria.objects.get(pk=pk)
    except Categoria.DoesNotExist:
        return JsonResponse({'error': 'Categoría no encontrada.'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'id': c.id, 'nombre': c.nombre, 'descripcion': c.descripcion}, status=200)

    return metodo_no_permitido_publico(['GET'])


@csrf_exempt
def marcas_collection_public(request):
    """API Base: Consulta pública de marcas (Solo GET)."""
    if request.method == 'GET':
        results = [{'id': m.id, 'nombre': m.nombre, 'pais_origen': m.pais_origen} for m in Marca.objects.all()]
        return JsonResponse({'results': results}, status=200)
    return metodo_no_permitido_publico(['GET'])


@csrf_exempt
def marca_detail_public(request, pk):
    """API Base: Detalle público de una marca (Solo GET)."""
    try:
        m = Marca.objects.get(pk=pk)
    except Marca.DoesNotExist:
        return JsonResponse({'error': 'Marca no encontrada.'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'id': m.id, 'nombre': m.nombre, 'pais_origen': m.pais_origen}, status=200)

    return metodo_no_permitido_publico(['GET'])
