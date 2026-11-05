from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # Conectamos todas las rutas de webapp a la raíz del sitio web
    path('', include('webapp.urls')),
]
