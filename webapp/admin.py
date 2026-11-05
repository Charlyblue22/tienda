from django.contrib import admin
from .models import Categoria, Marca, Producto, Venta, DetalleVenta, ConfiguracionTienda

admin.site.register(Categoria)
admin.site.register(Marca)
admin.site.register(Producto)
admin.site.register(Venta)
admin.site.register(DetalleVenta)
admin.site.register(ConfiguracionTienda)
