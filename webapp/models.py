from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Categoria(models.Model):
    nombre = models.CharField(max_length=60, unique=True)
    descripcion = models.TextField(blank=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'descripcion': self.descripcion,
            'total_productos': getattr(self, 'total_productos', self.productos.count()),
        }


class Marca(models.Model):
    nombre = models.CharField(max_length=60, unique=True)
    pais_origen = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'pais_origen': self.pais_origen,
            'total_productos': getattr(self, 'total_productos', self.productos.count()),
        }


class Producto(models.Model):
    ESPECIES = [
        ('perro', 'Perro'),
        ('gato', 'Gato'),
        ('ave', 'Ave'),
        ('roedor', 'Roedor'),
        ('todas', 'Todas'),
    ]

    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)
    precio = models.PositiveIntegerField(help_text='Precio en CLP')
    stock = models.PositiveIntegerField(default=0)
    especie = models.CharField(max_length=10, choices=ESPECIES, default='todas')
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, related_name='productos')
    marca = models.ForeignKey(Marca, on_delete=models.SET_NULL, null=True, blank=True, related_name='productos')
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'descripcion': self.descripcion,
            'precio': self.precio,
            'stock': self.stock,
            'especie': self.especie,
            'especie_display': self.get_especie_display(),
            'categoria': {'id': self.categoria_id, 'nombre': self.categoria.nombre},
            'marca': {'id': self.marca_id, 'nombre': self.marca.nombre} if self.marca else None,
            'creado': self.creado.isoformat(),
        }


class Venta(models.Model):
    ESTADOS = [
        ('completada', 'Completada'),
        ('pendiente', 'Pendiente'),
        ('cancelada', 'Cancelada'),
    ]
    METODOS_PAGO = [
        ('tarjeta', 'Tarjeta Débito / Crédito'),
        ('transferencia', 'Transferencia Bancaria'),
        ('efectivo', 'Efectivo'),
    ]

    folio = models.CharField(max_length=24, unique=True, blank=True)
    cliente_nombre = models.CharField(max_length=120, default='Cliente General')
    cliente_email = models.EmailField(blank=True)
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='ventas'
    )
    estado = models.CharField(max_length=15, choices=ESTADOS, default='completada')
    metodo_pago = models.CharField(max_length=20, choices=METODOS_PAGO, default='tarjeta')
    subtotal = models.PositiveIntegerField(default=0, help_text='Monto neto en CLP')
    iva = models.PositiveIntegerField(default=0, help_text='IVA (19%) en CLP')
    total = models.PositiveIntegerField(default=0, help_text='Monto total bruto en CLP')
    notas = models.TextField(blank=True)
    fecha = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f"{self.folio or f'VTA-{self.id}'} - {self.cliente_nombre} (${self.total})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.folio:
            self.folio = f"VTA-{1000 + self.id}"
            super().save(update_fields=['folio'])

    def recalcular_totales(self, iva_pct=19):
        total_bruto = sum(item.subtotal for item in self.detalles.all())
        neto = int(round(total_bruto / (1 + (iva_pct / 100.0)))) if total_bruto > 0 else 0
        iva_monto = max(0, total_bruto - neto)
        self.subtotal = neto
        self.iva = iva_monto
        self.total = total_bruto
        self.save(update_fields=['subtotal', 'iva', 'total'])

    def to_dict(self):
        detalles_list = [d.to_dict() for d in self.detalles.all()]
        return {
            'id': self.id,
            'folio': self.folio or f"VTA-{1000 + self.id}",
            'cliente_nombre': self.cliente_nombre,
            'cliente_email': self.cliente_email,
            'usuario': self.usuario.username if self.usuario else None,
            'estado': self.estado,
            'estado_display': self.get_estado_display(),
            'metodo_pago': self.metodo_pago,
            'metodo_pago_display': self.get_metodo_pago_display(),
            'subtotal': self.subtotal,
            'iva': self.iva,
            'total': self.total,
            'notas': self.notas,
            'fecha': self.fecha.isoformat(),
            'fecha_formateada': timezone.localtime(self.fecha).strftime('%d/%m/%Y %H:%M'),
            'detalles': detalles_list,
            'resumen_productos': ', '.join(f"{d['cantidad']}x {d['nombre_producto']}" for d in detalles_list),
            'cantidad_items': sum(d['cantidad'] for d in detalles_list),
        }


class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(
        Producto, on_delete=models.SET_NULL, null=True, blank=True, related_name='detalles_venta'
    )
    nombre_producto = models.CharField(max_length=120)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.PositiveIntegerField(help_text='Precio unitario en CLP')
    subtotal = models.PositiveIntegerField(help_text='Subtotal de la línea en CLP')

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.cantidad}x {self.nombre_producto}"

    def save(self, *args, **kwargs):
        self.subtotal = int(self.cantidad) * int(self.precio_unitario)
        super().save(*args, **kwargs)

    def to_dict(self):
        return {
            'id': self.id,
            'producto_id': self.producto_id,
            'nombre_producto': self.nombre_producto,
            'cantidad': self.cantidad,
            'precio_unitario': self.precio_unitario,
            'subtotal': self.subtotal,
        }


class ConfiguracionTienda(models.Model):
    nombre_tienda = models.CharField(max_length=100, default='Patitas Chile')
    slogan = models.CharField(max_length=200, default='Nutrición, salud y bienestar premium para tu mascota')
    email_contacto = models.EmailField(default='contacto@patitaschile.cl')
    telefono_contacto = models.CharField(max_length=30, default='+56 9 8450 3210')
    direccion = models.CharField(max_length=200, default='Av. Providencia 1450, Providencia, Santiago')
    horario_atencion = models.CharField(max_length=120, default='Lunes a Sábado: 09:00 a 20:00 hrs')
    iva_porcentaje = models.PositiveIntegerField(default=19)
    stock_minimo_alerta = models.PositiveIntegerField(default=10)
    envio_gratis_desde = models.PositiveIntegerField(default=35000)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuración de Tienda'
        verbose_name_plural = 'Configuraciones de Tienda'

    def __str__(self):
        return self.nombre_tienda

    @classmethod
    def obtener(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def to_dict(self):
        return {
            'nombre_tienda': self.nombre_tienda,
            'slogan': self.slogan,
            'email_contacto': self.email_contacto,
            'telefono_contacto': self.telefono_contacto,
            'direccion': self.direccion,
            'horario_atencion': self.horario_atencion,
            'iva_porcentaje': self.iva_porcentaje,
            'stock_minimo_alerta': self.stock_minimo_alerta,
            'envio_gratis_desde': self.envio_gratis_desde,
        }
