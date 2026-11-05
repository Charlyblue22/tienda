# webapp/api/urls.py
from django.urls import path, include
from .router import AdminAPIRouter
from . import public_views
from . import admin_views

# Router de administración: aplica IsSuperUserPermission automáticamente a nivel de router
admin_router = AdminAPIRouter()

# Registro de recursos en el router de administración (/api/admin/...)
admin_router.register('productos/', admin_views.admin_productos_collection, name='admin_api_productos')
admin_router.register('productos/<int:pk>/', admin_views.admin_producto_detail, name='admin_api_producto_detail')
admin_router.register('categorias/', admin_views.admin_categorias_collection, name='admin_api_categorias')
admin_router.register('categorias/<int:pk>/', admin_views.admin_categoria_detail, name='admin_api_categoria_detail')
admin_router.register('marcas/', admin_views.admin_marcas_collection, name='admin_api_marcas')
admin_router.register('marcas/<int:pk>/', admin_views.admin_marca_detail, name='admin_api_marca_detail')

# Métricas, Contabilidad de Ventas, Usuarios y Configuración (/api/admin/...)
admin_router.register('metricas/', admin_views.admin_metricas_dashboard, name='admin_api_metricas')
admin_router.register('ventas/', admin_views.admin_ventas_collection, name='admin_api_ventas')
admin_router.register('ventas/exportar-csv/', admin_views.admin_ventas_export_csv, name='admin_api_ventas_csv')
admin_router.register('ventas/<int:pk>/', admin_views.admin_venta_detail, name='admin_api_venta_detail')
admin_router.register('usuarios/', admin_views.admin_usuarios_collection, name='admin_api_usuarios')
admin_router.register('usuarios/<int:pk>/', admin_views.admin_usuario_detail, name='admin_api_usuario_detail')
admin_router.register('configuracion/', admin_views.admin_configuracion_view, name='admin_api_configuracion')

# Rutas públicas de consulta (/api/...)
public_patterns = [
    path('productos/', public_views.productos_collection_public, name='api_productos'),
    path('productos/<int:pk>/', public_views.producto_detail_public, name='api_producto_detail'),
    path('categorias/', public_views.categorias_collection_public, name='api_categorias'),
    path('categorias/<int:pk>/', public_views.categoria_detail_public, name='api_categoria_detail'),
    path('marcas/', public_views.marcas_collection_public, name='api_marcas'),
    path('marcas/<int:pk>/', public_views.marca_detail_public, name='api_marca_detail'),
]

urlpatterns = [
    # Router protegido para superusuarios: /api/admin/...
    path('admin/', include(admin_router.urls)),
    # API Base pública de lectura: /api/...
    path('', include(public_patterns)),
]
