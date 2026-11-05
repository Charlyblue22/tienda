# webapp/urls.py
from django.urls import path, include
from . import views

urlpatterns = [
    # ---------- Vistas públicas de la tienda ----------
    path('', views.portal_dashboard, name='portal_home'),
    path('productos/', views.lista_productos, name='lista_productos'),
    path('productos/<int:pk>/', views.detalle_producto, name='detalle_producto'),
    path('comprar/', views.comprar_producto, name='comprar_producto'),
    path('categorias/', views.lista_categorias, name='lista_categorias'),
    path('marcas/', views.lista_marcas, name='lista_marcas'),
    path('api-docs/', views.api_docs, name='api_docs'),
    path('api-docs/admin/', views.api_docs_admin, name='api_docs_admin'),

    # ---------- Rutas API REST Internas ----------
    path('api/', include('webapp.api.urls')),

    # ---------- Panel de Administración y Autenticación ----------
    path('admin-api/', views.admin_api_test, name='admin_api'),
    path('panel/', views.admin_api_test, name='panel_admin'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
]
