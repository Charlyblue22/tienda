/**
 * Patitas Chile · Controlador del Panel de Administración Integral
 * Gestiona Dashboard, Contabilidad de Ventas, CRUD (Productos, Categorías, Marcas),
 * Usuarios/Clientes y Configuración general.
 */

const AdminApp = (function () {
  // Estado interno
  let metricasData = null;
  let productosLista = [];
  let categoriasLista = [];
  let marcasLista = [];
  let ventasLista = [];
  let usuariosLista = [];

  // Estado de gráficos
  let chartPeriodoInstance = null;
  let chartCategoriaInstance = null;
  let chartPeriodoActual = 'dias_7';
  let chartTipoActual = 'bar';

  // Estado de paginación y filtros de productos
  let prodPaginaActual = 1;
  let prodPorPagina = 10;
  let prodOrdenActual = 'nombre';
  let periodoVentasRapido = '';

  // Formateador de moneda CLP
  function fmtCLP(valor) {
    const num = Number(valor) || 0;
    return '$' + num.toLocaleString('es-CL');
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function badgeEstadoVenta(estado, display) {
    const mapa = {
      completada: 'badge-soft-success',
      pendiente: 'badge-soft-warning',
      cancelada: 'badge-soft-danger'
    };
    const iconos = {
      completada: 'bi-check-circle-fill',
      pendiente: 'bi-clock-history',
      cancelada: 'bi-x-circle-fill'
    };
    const cls = mapa[estado] || 'badge-soft-info';
    const ico = iconos[estado] || 'bi-circle';
    return `<span class="badge ${cls} rounded-pill px-2 py-1"><i class="bi ${ico} me-1"></i>${escapeHtml(display || estado)}</span>`;
  }

  // Petición HTTP genérica hacia la API de administración
  async function apiFetch(url, options = {}) {
    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {})
      },
      ...options
    };
    const response = await fetch(url, config);
    if (response.status === 204) {
      return { ok: true, status: 204, data: null };
    }
    let data = null;
    try {
      data = await response.json();
    } catch (_) {
      data = null;
    }
    return { ok: response.ok, status: response.status, data };
  }

  // ===================================================================
  // NAVEGACIÓN ENTRE SECCIONES DEL SIDEBAR
  // ===================================================================
  function cambiarSeccion(seccion) {
    const seccionesValidas = ['dashboard', 'ventas', 'productos', 'categorias', 'marcas', 'usuarios', 'configuracion'];
    const target = seccionesValidas.includes(seccion) ? seccion : 'dashboard';

    document.querySelectorAll('.admin-nav-btn').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-section') === target);
    });

    document.querySelectorAll('.admin-section').forEach(sec => {
      sec.classList.toggle('d-none', sec.id !== `sec-${target}`);
    });

    const url = new URL(window.location);
    url.searchParams.set('seccion', target);
    window.history.replaceState({}, '', url);

    if (target === 'dashboard') cargarMetricasDashboard(false);
    if (target === 'ventas') cargarVentas();
    if (target === 'productos') cargarProductos();
    if (target === 'categorias') cargarCategorias();
    if (target === 'marcas') cargarMarcas();
    if (target === 'usuarios') cargarUsuarios();
  }

  // ===================================================================
  // A) DASHBOARD EJECUTIVO Y GRÁFICOS
  // ===================================================================
  async function cargarMetricasDashboard(notificar = false) {
    const res = await apiFetch('/api/admin/metricas/');
    if (!res.ok || !res.data) {
      window.mostrarToast('No fue posible actualizar las métricas del dashboard.', 'error');
      return;
    }
    metricasData = res.data;
    const m = metricasData;

    // Actualizar KPIs
    const setTxt = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val;
    };

    setTxt('kpiTotalMonto', fmtCLP(m.total_ventas_monto));
    setTxt('kpiTicketPromedio', fmtCLP(m.ticket_promedio));
    setTxt('kpiNumeroVentas', m.numero_ventas);
    setTxt('kpiVentasPendientes', m.ventas_pendientes);
    setTxt('kpiVentasCanceladas', m.ventas_canceladas);

    if (m.producto_mas_vendido) {
      setTxt('kpiTopProductoNombre', m.producto_mas_vendido.nombre_producto);
      setTxt('kpiTopProductoUnidades', m.producto_mas_vendido.unidades);
      setTxt('kpiTopProductoIngresos', fmtCLP(m.producto_mas_vendido.ingresos));
    }

    setTxt('kpiTotalProductos', m.total_productos);
    setTxt('kpiUnidadesStock', m.unidades_stock);
    setTxt('kpiBajoStockCount', m.productos_bajo_stock_count);

    setTxt('kpiHoyMonto', fmtCLP(m.ventas_hoy.monto));
    setTxt('kpiHoyCantidad', m.ventas_hoy.cantidad);
    setTxt('kpiSemanaMonto', fmtCLP(m.ventas_semana.monto));
    setTxt('kpiSemanaCantidad', m.ventas_semana.cantidad);
    setTxt('kpiMesMonto', fmtCLP(m.ventas_mes.monto));
    setTxt('kpiMesCantidad', m.ventas_mes.cantidad);

    // Badges del sidebar
    setTxt('navBadgeVentas', m.numero_ventas);
    setTxt('navBadgeProductos', m.total_productos);
    setTxt('navBadgeCategorias', m.total_categorias);
    setTxt('navBadgeMarcas', m.total_marcas);
    setTxt('navBadgeUsuarios', m.total_usuarios);

    renderizarGraficoPeriodo();
    renderizarGraficoCategorias();
    renderizarTopProductos(m.top_productos || []);
    renderizarUltimasVentas(m.ultimas_ventas || []);

    if (notificar) {
      window.mostrarToast('Métricas y gráficos actualizados correctamente.', 'info');
    }
  }

  function renderizarGraficoPeriodo() {
    if (!metricasData || !window.Chart) return;
    const canvas = document.getElementById('ventasPeriodoChart');
    if (!canvas) return;

    const serie = metricasData.series[chartPeriodoActual] || metricasData.series.dias_7;
    const isDark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
    const textColor = isDark ? '#cbd5e1' : '#475569';
    const gridColor = isDark ? 'rgba(148, 163, 184, 0.12)' : 'rgba(15, 23, 42, 0.06)';

    if (chartPeriodoInstance) {
      chartPeriodoInstance.destroy();
    }

    chartPeriodoInstance = new Chart(canvas, {
      type: chartTipoActual,
      data: {
        labels: serie.labels,
        datasets: [
          {
            label: 'Ingresos CLP',
            data: serie.ingresos,
            backgroundColor: chartTipoActual === 'bar' ? 'rgba(255, 90, 54, 0.82)' : 'rgba(255, 90, 54, 0.16)',
            borderColor: '#ff5a36',
            borderWidth: 2.5,
            borderRadius: chartTipoActual === 'bar' ? 8 : 0,
            tension: 0.35,
            fill: chartTipoActual === 'line',
            pointBackgroundColor: '#ff5a36',
            pointRadius: 4
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                const idx = ctx.dataIndex;
                const cant = serie.cantidades[idx] || 0;
                return ` ${fmtCLP(ctx.parsed.y)} (${cant} venta${cant === 1 ? '' : 's'})`;
              }
            }
          }
        },
        scales: {
          x: {
            ticks: { color: textColor, font: { size: 11 } },
            grid: { display: false }
          },
          y: {
            beginAtZero: true,
            ticks: {
              color: textColor,
              font: { size: 11 },
              callback: function (val) {
                return '$' + Number(val).toLocaleString('es-CL');
              }
            },
            grid: { color: gridColor }
          }
        }
      }
    });
  }

  function renderizarGraficoCategorias() {
    if (!metricasData || !window.Chart) return;
    const canvas = document.getElementById('ventasCategoriaChart');
    if (!canvas) return;

    const vc = metricasData.ventas_por_categoria || { labels: [], ingresos: [] };
    const isDark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
    const textColor = isDark ? '#cbd5e1' : '#475569';

    if (chartCategoriaInstance) {
      chartCategoriaInstance.destroy();
    }

    chartCategoriaInstance = new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels: vc.labels,
        datasets: [
          {
            data: vc.ingresos,
            backgroundColor: ['#ff5a36', '#0d9488', '#4f46e5', '#f59e0b', '#10b981'],
            borderWidth: 0,
            hoverOffset: 6
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '66%',
        plugins: {
          legend: {
            position: 'bottom',
            labels: { color: textColor, boxWidth: 12, padding: 12, font: { size: 11 } }
          },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                return ` ${ctx.label}: ${fmtCLP(ctx.parsed)}`;
              }
            }
          }
        }
      }
    });
  }

  function renderizarTopProductos(lista) {
    const container = document.getElementById('topProductosList');
    if (!container) return;
    if (!lista.length) {
      container.innerHTML = '<div class="text-muted small">Sin ventas registradas aún.</div>';
      return;
    }
    container.innerHTML = lista.slice(0, 4).map((item, idx) => `
      <div class="d-flex justify-content-between align-items-center py-1 border-bottom">
        <div class="text-truncate pe-2">
          <span class="badge badge-soft-primary me-1">${idx + 1}</span>
          <span class="fw-semibold">${escapeHtml(item.nombre_producto)}</span>
        </div>
        <div class="text-nowrap">
          <span class="text-muted me-2">${item.unidades} uds.</span>
          <strong class="text-primary">${fmtCLP(item.ingresos)}</strong>
        </div>
      </div>
    `).join('');
  }

  function renderizarUltimasVentas(ventas) {
    const tbody = document.getElementById('tablaUltimasVentasBody');
    if (!tbody) return;
    if (!ventas.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-center py-4 text-secondary">No hay ventas registradas aún.</td></tr>';
      return;
    }
    tbody.innerHTML = ventas.map(v => `
      <tr>
        <td><span class="fw-bold text-primary">${escapeHtml(v.folio)}</span></td>
        <td class="small text-secondary">${escapeHtml(v.fecha_formateada)}</td>
        <td>
          <div class="fw-semibold">${escapeHtml(v.cliente_nombre)}</div>
          <div class="small text-muted">${escapeHtml(v.cliente_email || '')}</div>
        </td>
        <td class="small text-secondary" style="max-width: 260px;">
          <div class="text-truncate" title="${escapeHtml(v.resumen_productos)}">${escapeHtml(v.resumen_productos)}</div>
        </td>
        <td><span class="small">${escapeHtml(v.metodo_pago_display)}</span></td>
        <td>${badgeEstadoVenta(v.estado, v.estado_display)}</td>
        <td class="text-end fw-bold">${fmtCLP(v.total)}</td>
        <td class="text-end">
          <button type="button" class="btn btn-sm btn-outline-secondary py-1 px-2" onclick="AdminApp.verDetalleVenta(${v.id})" title="Ver comprobante">
            <i class="bi bi-eye"></i>
          </button>
        </td>
      </tr>
    `).join('');
  }

  // ===================================================================
  // B) CONTABILIDAD DE VENTAS + POS + EXPORTACIÓN CSV
  // ===================================================================
  function obtenerParametrosFiltroVentas() {
    const params = new URLSearchParams();
    const q = (document.getElementById('ventaFiltroBuscar')?.value || '').trim();
    const desde = document.getElementById('ventaFiltroDesde')?.value || '';
    const hasta = document.getElementById('ventaFiltroHasta')?.value || '';
    const producto = document.getElementById('ventaFiltroProducto')?.value || '';
    const estado = document.getElementById('ventaFiltroEstado')?.value || '';

    if (q) params.set('q', q);
    if (desde) params.set('fecha_desde', desde);
    if (hasta) params.set('fecha_hasta', hasta);
    if (producto) params.set('producto', producto);
    if (estado) params.set('estado', estado);
    if (periodoVentasRapido) params.set('periodo', periodoVentasRapido);
    return params;
  }

  async function cargarVentas() {
    const params = obtenerParametrosFiltroVentas();
    const res = await apiFetch(`/api/admin/ventas/?${params.toString()}`);
    if (!res.ok || !res.data) {
      window.mostrarToast('Error al cargar el libro de ventas.', 'error');
      return;
    }

    ventasLista = res.data.results || [];
    const r = res.data.resumen || {};

    // Actualizar tarjetas contables y pie de tabla
    const setTxt = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val;
    };

    setTxt('contableSubtotalNeto', fmtCLP(r.subtotal_neto));
    setTxt('contableIvaTotal', fmtCLP(r.iva_total));
    setTxt('contableTotalBruto', fmtCLP(r.total_bruto));
    setTxt('contableCantidad', r.cantidad_computables);
    setTxt('contableTicketProm', fmtCLP(r.ticket_promedio));
    setTxt('ventasCountLabel', ventasLista.length);

    setTxt('tfootSubtotalNeto', fmtCLP(r.subtotal_neto));
    setTxt('tfootIvaTotal', fmtCLP(r.iva_total));
    setTxt('tfootTotalBruto', fmtCLP(r.total_bruto));

    const tbody = document.getElementById('tablaContabilidadBody');
    if (!tbody) return;

    if (!ventasLista.length) {
      tbody.innerHTML = `
        <tr>
          <td colspan="10" class="text-center py-5 text-secondary">
            <i class="bi bi-receipt fs-2 d-block mb-2 text-muted"></i>
            No se encontraron ventas para los filtros seleccionados.
          </td>
        </tr>`;
      return;
    }

    tbody.innerHTML = ventasLista.map(v => `
      <tr class="${v.estado === 'cancelada' ? 'opacity-50' : ''}">
        <td><span class="fw-bold text-primary">${escapeHtml(v.folio)}</span></td>
        <td class="small text-secondary text-nowrap">${escapeHtml(v.fecha_formateada)}</td>
        <td>
          <div class="fw-semibold">${escapeHtml(v.cliente_nombre)}</div>
          <div class="small text-muted">${escapeHtml(v.cliente_email || 'Sin correo')}</div>
        </td>
        <td class="small" style="max-width: 250px;">
          <div class="text-truncate" title="${escapeHtml(v.resumen_productos)}">${escapeHtml(v.resumen_productos)}</div>
          <span class="text-muted" style="font-size: 0.72rem;">${v.cantidad_items} unidad(es)</span>
        </td>
        <td class="small">${escapeHtml(v.metodo_pago_display)}</td>
        <td>
          <select class="form-select form-select-sm py-1" style="width: 135px; font-size: 0.8rem;"
                  onchange="AdminApp.cambiarEstadoVenta(${v.id}, this.value)" aria-label="Estado de venta ${escapeHtml(v.folio)}">
            <option value="completada" ${v.estado === 'completada' ? 'selected' : ''}>Completada</option>
            <option value="pendiente" ${v.estado === 'pendiente' ? 'selected' : ''}>Pendiente</option>
            <option value="cancelada" ${v.estado === 'cancelada' ? 'selected' : ''}>Cancelada</option>
          </select>
        </td>
        <td class="text-end">${fmtCLP(v.subtotal)}</td>
        <td class="text-end text-secondary">${fmtCLP(v.iva)}</td>
        <td class="text-end fw-bold text-primary">${fmtCLP(v.total)}</td>
        <td class="text-end text-nowrap">
          <button type="button" class="btn btn-sm btn-outline-secondary py-1 px-2 me-1" onclick="AdminApp.verDetalleVenta(${v.id})" title="Ver detalle">
            <i class="bi bi-eye"></i>
          </button>
          <button type="button" class="btn btn-sm btn-outline-danger py-1 px-2" onclick="AdminApp.confirmarEliminar('venta', ${v.id}, '${escapeHtml(v.folio)}')" title="Eliminar registro">
            <i class="bi bi-trash3"></i>
          </button>
        </td>
      </tr>
    `).join('');
  }

  function filtrarPeriodoVentas(periodo) {
    periodoVentasRapido = periodo;
    if (periodo) {
      document.getElementById('ventaFiltroDesde').value = '';
      document.getElementById('ventaFiltroHasta').value = '';
    }
    cargarVentas();
  }

  function limpiarFiltrosVentas() {
    periodoVentasRapido = '';
    document.getElementById('ventaFiltroBuscar').value = '';
    document.getElementById('ventaFiltroDesde').value = '';
    document.getElementById('ventaFiltroHasta').value = '';
    document.getElementById('ventaFiltroProducto').value = '';
    document.getElementById('ventaFiltroEstado').value = '';
    cargarVentas();
  }

  function exportarVentasCSV() {
    const params = obtenerParametrosFiltroVentas();
    const url = `/api/admin/ventas/exportar-csv/?${params.toString()}`;
    window.location.href = url;
    window.mostrarToast('Generando archivo CSV / Excel de contabilidad...', 'info');
  }

  async function cambiarEstadoVenta(id, nuevoEstado) {
    const res = await apiFetch(`/api/admin/ventas/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify({ estado: nuevoEstado })
    });
    if (!res.ok) {
      window.mostrarToast(res.data?.detalle || res.data?.error || 'No se pudo cambiar el estado.', 'error');
      cargarVentas();
      return;
    }
    window.mostrarToast(`Estado de ${res.data.folio} actualizado a ${res.data.estado_display}.`, 'success');
    cargarVentas();
    cargarMetricasDashboard(false);
  }

  async function verDetalleVenta(id) {
    const res = await apiFetch(`/api/admin/ventas/${id}/`);
    if (!res.ok || !res.data) {
      window.mostrarToast('No se pudo cargar el comprobante.', 'error');
      return;
    }
    const v = res.data;
    document.getElementById('modalDetalleVentaTitle').textContent = `Comprobante ${v.folio}`;
    const filas = (v.detalles || []).map(d => `
      <tr>
        <td>${escapeHtml(d.nombre_producto)}</td>
        <td class="text-center">${d.cantidad}</td>
        <td class="text-end">${fmtCLP(d.precio_unitario)}</td>
        <td class="text-end fw-semibold">${fmtCLP(d.subtotal)}</td>
      </tr>
    `).join('');

    document.getElementById('modalDetalleVentaBody').innerHTML = `
      <div class="d-flex justify-content-between align-items-start mb-3 pb-3 border-bottom">
        <div>
          <div class="small text-muted">Cliente</div>
          <div class="fw-bold">${escapeHtml(v.cliente_nombre)}</div>
          <div class="small text-secondary">${escapeHtml(v.cliente_email || 'Sin correo registrado')}</div>
        </div>
        <div class="text-end">
          <div class="small text-muted">${escapeHtml(v.fecha_formateada)}</div>
          <div class="mt-1">${badgeEstadoVenta(v.estado, v.estado_display)}</div>
        </div>
      </div>
      <div class="table-responsive mb-3">
        <table class="table table-sm align-middle mb-0">
          <thead>
            <tr class="small text-muted">
              <th>Producto</th>
              <th class="text-center">Cant.</th>
              <th class="text-end">Unitario</th>
              <th class="text-end">Subtotal</th>
            </tr>
          </thead>
          <tbody>${filas}</tbody>
        </table>
      </div>
      <div class="p-3 rounded-3" style="background-color: var(--bg-surface-alt);">
        <div class="d-flex justify-content-between small mb-1">
          <span class="text-secondary">Método de pago:</span>
          <strong>${escapeHtml(v.metodo_pago_display)}</strong>
        </div>
        <div class="d-flex justify-content-between small mb-1">
          <span class="text-secondary">Subtotal Neto:</span>
          <span>${fmtCLP(v.subtotal)}</span>
        </div>
        <div class="d-flex justify-content-between small mb-2">
          <span class="text-secondary">IVA (19%):</span>
          <span>${fmtCLP(v.iva)}</span>
        </div>
        <div class="d-flex justify-content-between fw-bold fs-5 text-primary border-top pt-2">
          <span>Total Pagado:</span>
          <span>${fmtCLP(v.total)}</span>
        </div>
      </div>
      ${v.notas ? `<div class="small text-secondary mt-3"><strong>Notas:</strong> ${escapeHtml(v.notas)}</div>` : ''}
    `;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('modalDetalleVenta')).show();
  }

  // Modal Punto de Venta (POS)
  async function abrirModalNuevaVenta() {
    if (!productosLista.length) {
      const res = await apiFetch('/api/admin/productos/');
      if (res.ok && res.data) productosLista = res.data.results || [];
    }
    document.getElementById('ventaClienteNombre').value = '';
    document.getElementById('ventaClienteEmail').value = '';
    document.getElementById('ventaMetodoPago').value = 'tarjeta';
    document.getElementById('ventaEstadoSelect').value = 'completada';
    document.getElementById('ventaNotasInput').value = '';

    const container = document.getElementById('lineasVentaContainer');
    container.innerHTML = '';
    agregarLineaVenta();
    recalcularTotalesPOS();
    bootstrap.Modal.getOrCreateInstance(document.getElementById('modalNuevaVenta')).show();
  }

  function agregarLineaVenta() {
    const container = document.getElementById('lineasVentaContainer');
    const opciones = productosLista.map(p => `
      <option value="${p.id}" data-precio="${p.precio}" ${p.stock <= 0 ? 'disabled' : ''}>
        ${escapeHtml(p.nombre)} — ${fmtCLP(p.precio)} (${p.stock} disp.)
      </option>
    `).join('');

    const row = document.createElement('div');
    row.className = 'row g-2 align-items-center linea-venta-item';
    row.innerHTML = `
      <div class="col-7 col-sm-8">
        <select class="form-select form-select-sm pos-prod-select" onchange="AdminApp.recalcularTotalesPOS()" required>
          ${opciones}
        </select>
      </div>
      <div class="col-3 col-sm-2">
        <input type="number" class="form-control form-control-sm pos-cant-input" value="1" min="1" max="99" onchange="AdminApp.recalcularTotalesPOS()" oninput="AdminApp.recalcularTotalesPOS()" required>
      </div>
      <div class="col-2 col-sm-2 text-end">
        <button type="button" class="btn btn-sm btn-outline-danger" onclick="this.closest('.linea-venta-item').remove(); AdminApp.recalcularTotalesPOS();" title="Quitar línea">
          <i class="bi bi-x-lg"></i>
        </button>
      </div>
    `;
    container.appendChild(row);
    recalcularTotalesPOS();
  }

  function recalcularTotalesPOS() {
    let totalBruto = 0;
    document.querySelectorAll('.linea-venta-item').forEach(row => {
      const sel = row.querySelector('.pos-prod-select');
      const cantInput = row.querySelector('.pos-cant-input');
      const opt = sel?.selectedOptions?.[0];
      const precio = Number(opt?.getAttribute('data-precio') || 0);
      const cant = Math.max(1, Number(cantInput?.value || 1));
      totalBruto += precio * cant;
    });
    const neto = Math.round(totalBruto / 1.19);
    const iva = Math.max(0, totalBruto - neto);

    document.getElementById('posSubtotalNeto').textContent = fmtCLP(neto);
    document.getElementById('posIva').textContent = fmtCLP(iva);
    document.getElementById('posTotalBruto').textContent = fmtCLP(totalBruto);
  }

  async function guardarNuevaVenta() {
    const items = [];
    document.querySelectorAll('.linea-venta-item').forEach(row => {
      const prodId = Number(row.querySelector('.pos-prod-select')?.value);
      const cant = Number(row.querySelector('.pos-cant-input')?.value || 1);
      if (prodId && cant > 0) {
        items.push({ producto_id: prodId, cantidad: cant });
      }
    });

    if (!items.length) {
      window.mostrarToast('Agrega al menos un producto a la venta.', 'warning');
      return;
    }

    const payload = {
      cliente_nombre: document.getElementById('ventaClienteNombre').value.trim(),
      cliente_email: document.getElementById('ventaClienteEmail').value.trim(),
      metodo_pago: document.getElementById('ventaMetodoPago').value,
      estado: document.getElementById('ventaEstadoSelect').value,
      notas: document.getElementById('ventaNotasInput').value.trim(),
      items
    };

    const res = await apiFetch('/api/admin/ventas/', {
      method: 'POST',
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      window.mostrarToast(res.data?.detalle || res.data?.error || 'Error al registrar la venta.', 'error');
      return;
    }

    bootstrap.Modal.getInstance(document.getElementById('modalNuevaVenta'))?.hide();
    window.mostrarToast(`Venta ${res.data.folio} registrada por ${fmtCLP(res.data.total)}.`, 'success');
    cargarMetricasDashboard(false);
    cargarVentas();
    cargarProductos();
  }

  // ===================================================================
  // C) GESTIÓN CRUD DE PRODUCTOS, CATEGORÍAS Y MARCAS
  // ===================================================================
  async function cargarCatalogosAuxiliares() {
    const [resCat, resMar] = await Promise.all([
      apiFetch('/api/admin/categorias/'),
      apiFetch('/api/admin/marcas/')
    ]);
    if (resCat.ok && resCat.data) categoriasLista = resCat.data.results || [];
    if (resMar.ok && resMar.data) marcasLista = resMar.data.results || [];

    // Poblar selects de categorías y marcas en filtros y modal
    const filtroCat = document.getElementById('prodFiltroCat');
    if (filtroCat) {
      const valActual = filtroCat.value;
      filtroCat.innerHTML = '<option value="">Todas</option>' +
        categoriasLista.map(c => `<option value="${c.id}">${escapeHtml(c.nombre)}</option>`).join('');
      filtroCat.value = valActual;
    }

    const modalCat = document.getElementById('prodCategoriaInput');
    if (modalCat) {
      modalCat.innerHTML = categoriasLista.map(c => `<option value="${c.id}">${escapeHtml(c.nombre)}</option>`).join('');
    }

    const modalMarca = document.getElementById('prodMarcaInput');
    if (modalMarca) {
      modalMarca.innerHTML = '<option value="">— Sin marca específica —</option>' +
        marcasLista.map(m => `<option value="${m.id}">${escapeHtml(m.nombre)}</option>`).join('');
    }
  }

  async function cargarProductos() {
    await cargarCatalogosAuxiliares();
    const params = new URLSearchParams();
    const q = (document.getElementById('prodBuscarInput')?.value || '').trim();
    const cat = document.getElementById('prodFiltroCat')?.value || '';
    const esp = document.getElementById('prodFiltroEspecie')?.value || '';
    const stock = document.getElementById('prodFiltroStock')?.value || '';
    const orden = document.getElementById('prodOrdenSelect')?.value || prodOrdenActual;

    if (q) params.set('q', q);
    if (cat) params.set('categoria', cat);
    if (esp) params.set('especie', esp);
    if (stock) params.set('stock_estado', stock);
    if (orden) params.set('orden', orden);

    const res = await apiFetch(`/api/admin/productos/?${params.toString()}`);
    if (!res.ok || !res.data) {
      window.mostrarToast('Error al cargar productos.', 'error');
      return;
    }
    productosLista = res.data.results || [];
    document.getElementById('navBadgeProductos').textContent = productosLista.length;
    prodPaginaActual = 1;
    renderizarTablaProductos();
  }

  function renderizarTablaProductos() {
    const tbody = document.getElementById('tablaProductosAdminBody');
    if (!tbody) return;

    const total = productosLista.length;
    const totalPaginas = Math.max(1, Math.ceil(total / prodPorPagina));
    if (prodPaginaActual > totalPaginas) prodPaginaActual = totalPaginas;

    const inicio = (prodPaginaActual - 1) * prodPorPagina;
    const fin = Math.min(inicio + prodPorPagina, total);
    const paginaItems = productosLista.slice(inicio, fin);

    const infoEl = document.getElementById('prodPaginationInfo');
    if (infoEl) {
      infoEl.textContent = total > 0 ? `Mostrando ${inicio + 1}-${fin} de ${total}` : '0 resultados';
    }

    if (!paginaItems.length) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center py-5 text-secondary">
            <i class="bi bi-box-seam fs-2 d-block mb-2 text-muted"></i>
            No se encontraron productos con esos criterios.
          </td>
        </tr>`;
      document.getElementById('prodPaginationControls').innerHTML = '';
      return;
    }

    tbody.innerHTML = paginaItems.map(p => {
      let stockBadge = `<span class="badge badge-soft-success rounded-pill">${p.stock} uds.</span>`;
      if (p.stock === 0) {
        stockBadge = `<span class="badge badge-soft-danger rounded-pill">Agotado (0)</span>`;
      } else if (p.stock <= 10) {
        stockBadge = `<span class="badge badge-soft-warning rounded-pill">Bajo (${p.stock})</span>`;
      }

      return `
        <tr>
          <td class="text-muted small">#${p.id}</td>
          <td>
            <div class="fw-bold">${escapeHtml(p.nombre)}</div>
            <div class="small text-secondary text-truncate" style="max-width: 280px;">${escapeHtml(p.descripcion || 'Sin descripción')}</div>
          </td>
          <td>
            <span class="badge badge-soft-primary me-1">${escapeHtml(p.categoria?.nombre || '')}</span>
            <span class="badge bg-secondary-subtle text-secondary">${escapeHtml(p.especie_display || p.especie)}</span>
          </td>
          <td class="small">${escapeHtml(p.marca?.nombre || '—')}</td>
          <td class="text-end fw-bold text-primary">${fmtCLP(p.precio)}</td>
          <td class="text-center">
            <div class="d-inline-flex align-items-center gap-1">
              <button type="button" class="btn btn-sm btn-outline-secondary py-0 px-1" onclick="AdminApp.ajustarStockRapido(${p.id}, ${Math.max(0, p.stock - 1)})" title="Restar 1">-</button>
              ${stockBadge}
              <button type="button" class="btn btn-sm btn-outline-secondary py-0 px-1" onclick="AdminApp.ajustarStockRapido(${p.id}, ${p.stock + 1})" title="Sumar 1">+</button>
            </div>
          </td>
          <td class="text-end text-nowrap">
            <button type="button" class="btn btn-sm btn-outline-primary py-1 px-2 me-1" onclick="AdminApp.abrirModalProducto(${p.id})" title="Editar producto">
              <i class="bi bi-pencil-square"></i>
            </button>
            <button type="button" class="btn btn-sm btn-outline-danger py-1 px-2" onclick="AdminApp.confirmarEliminar('producto', ${p.id}, '${escapeHtml(p.nombre)}')" title="Eliminar producto">
              <i class="bi bi-trash3"></i>
            </button>
          </td>
        </tr>
      `;
    }).join('');

    // Controles de paginación
    const pagContainer = document.getElementById('prodPaginationControls');
    if (pagContainer) {
      let html = `
        <button type="button" class="btn btn-outline-secondary" ${prodPaginaActual <= 1 ? 'disabled' : ''} onclick="AdminApp.irPaginaProductos(${prodPaginaActual - 1})">
          <i class="bi bi-chevron-left"></i>
        </button>`;
      for (let i = 1; i <= totalPaginas; i++) {
        html += `<button type="button" class="btn ${i === prodPaginaActual ? 'btn-primary' : 'btn-outline-secondary'}" onclick="AdminApp.irPaginaProductos(${i})">${i}</button>`;
      }
      html += `
        <button type="button" class="btn btn-outline-secondary" ${prodPaginaActual >= totalPaginas ? 'disabled' : ''} onclick="AdminApp.irPaginaProductos(${prodPaginaActual + 1})">
          <i class="bi bi-chevron-right"></i>
        </button>`;
      pagContainer.innerHTML = html;
    }
  }

  function irPaginaProductos(num) {
    prodPaginaActual = num;
    renderizarTablaProductos();
  }

  function cambiarOrdenProductos(campo) {
    const select = document.getElementById('prodOrdenSelect');
    if (select) {
      if (select.value === campo && campo === 'nombre') select.value = '-nombre';
      else if (select.value === 'precio_asc' && campo === 'precio_asc') select.value = 'precio_desc';
      else if (select.value === 'stock_asc' && campo === 'stock_asc') select.value = 'stock_desc';
      else select.value = campo;
    }
    prodOrdenActual = select ? select.value : campo;
    cargarProductos();
  }

  async function ajustarStockRapido(id, nuevoStock) {
    const res = await apiFetch(`/api/admin/productos/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify({ stock: nuevoStock })
    });
    if (!res.ok) {
      window.mostrarToast('No se pudo actualizar el stock.', 'error');
      return;
    }
    const idx = productosLista.findIndex(p => p.id === id);
    if (idx !== -1) productosLista[idx] = res.data;
    renderizarTablaProductos();
    window.mostrarToast(`Stock de "${res.data.nombre}" ajustado a ${res.data.stock} uds.`, 'success');
  }

  async function abrirModalProducto(id = null) {
    await cargarCatalogosAuxiliares();
    const modalEl = document.getElementById('modalProducto');
    if (id) {
      const prod = productosLista.find(p => p.id === id);
      if (!prod) return;
      document.getElementById('modalProductoTitle').textContent = `Editar Producto #${prod.id}`;
      document.getElementById('prodIdInput').value = prod.id;
      document.getElementById('prodNombreInput').value = prod.nombre;
      document.getElementById('prodEspecieInput').value = prod.especie;
      document.getElementById('prodCategoriaInput').value = prod.categoria?.id || '';
      document.getElementById('prodMarcaInput').value = prod.marca?.id || '';
      document.getElementById('prodPrecioInput').value = prod.precio;
      document.getElementById('prodStockInput').value = prod.stock;
      document.getElementById('prodDescInput').value = prod.descripcion || '';
    } else {
      document.getElementById('modalProductoTitle').textContent = 'Crear Nuevo Producto';
      document.getElementById('prodIdInput').value = '';
      document.getElementById('prodNombreInput').value = '';
      document.getElementById('prodEspecieInput').value = 'perro';
      if (categoriasLista.length) {
        document.getElementById('prodCategoriaInput').value = categoriasLista[0].id;
      }
      document.getElementById('prodMarcaInput').value = '';
      document.getElementById('prodPrecioInput').value = '';
      document.getElementById('prodStockInput').value = 15;
      document.getElementById('prodDescInput').value = '';
    }
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  async function guardarProducto() {
    const id = document.getElementById('prodIdInput').value;
    const nombre = document.getElementById('prodNombreInput').value.trim();
    const precio = Number(document.getElementById('prodPrecioInput').value);
    const stock = Number(document.getElementById('prodStockInput').value);
    const categoria_id = Number(document.getElementById('prodCategoriaInput').value);
    const marcaVal = document.getElementById('prodMarcaInput').value;
    const marca_id = marcaVal ? Number(marcaVal) : null;
    const especie = document.getElementById('prodEspecieInput').value;
    const descripcion = document.getElementById('prodDescInput').value.trim();

    if (!nombre || precio <= 0 || stock < 0 || !categoria_id) {
      window.mostrarToast('Por favor completa los campos obligatorios con valores válidos.', 'warning');
      return;
    }

    const payload = { nombre, descripcion, precio, stock, especie, categoria_id, marca_id };
    const url = id ? `/api/admin/productos/${id}/` : '/api/admin/productos/';
    const method = id ? 'PUT' : 'POST';

    const res = await apiFetch(url, { method, body: JSON.stringify(payload) });
    if (!res.ok) {
      window.mostrarToast(res.data?.detalle || res.data?.error || 'Error al guardar el producto.', 'error');
      return;
    }

    bootstrap.Modal.getInstance(document.getElementById('modalProducto'))?.hide();
    window.mostrarToast(
      id ? `Producto "${res.data.nombre}" actualizado correctamente.` : `Producto "${res.data.nombre}" creado con éxito.`,
      'success'
    );
    cargarProductos();
    cargarMetricasDashboard(false);
  }

  // ---------- Categorías CRUD ----------
  async function cargarCategorias() {
    const res = await apiFetch('/api/admin/categorias/');
    if (!res.ok || !res.data) return;
    categoriasLista = res.data.results || [];
    document.getElementById('navBadgeCategorias').textContent = categoriasLista.length;

    const tbody = document.getElementById('tablaCategoriasAdminBody');
    if (!tbody) return;
    if (!categoriasLista.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-secondary">No hay categorías registradas.</td></tr>';
      return;
    }

    tbody.innerHTML = categoriasLista.map(c => `
      <tr>
        <td class="text-muted small">#${c.id}</td>
        <td class="fw-bold">${escapeHtml(c.nombre)}</td>
        <td class="small text-secondary">${escapeHtml(c.descripcion || 'Sin descripción')}</td>
        <td class="text-center"><span class="badge badge-soft-primary rounded-pill px-3">${c.total_productos || 0}</span></td>
        <td class="text-end text-nowrap">
          <button type="button" class="btn btn-sm btn-outline-primary py-1 px-2 me-1" onclick="AdminApp.abrirModalCategoria(${c.id})">
            <i class="bi bi-pencil-square"></i>
          </button>
          <button type="button" class="btn btn-sm btn-outline-danger py-1 px-2" onclick="AdminApp.confirmarEliminar('categoria', ${c.id}, '${escapeHtml(c.nombre)}')">
            <i class="bi bi-trash3"></i>
          </button>
        </td>
      </tr>
    `).join('');
  }

  function abrirModalCategoria(id = null) {
    if (id) {
      const cat = categoriasLista.find(c => c.id === id);
      if (!cat) return;
      document.getElementById('modalCategoriaTitle').textContent = `Editar Categoría #${cat.id}`;
      document.getElementById('catIdInput').value = cat.id;
      document.getElementById('catNombreInput').value = cat.nombre;
      document.getElementById('catDescInput').value = cat.descripcion || '';
    } else {
      document.getElementById('modalCategoriaTitle').textContent = 'Nueva Categoría';
      document.getElementById('catIdInput').value = '';
      document.getElementById('catNombreInput').value = '';
      document.getElementById('catDescInput').value = '';
    }
    bootstrap.Modal.getOrCreateInstance(document.getElementById('modalCategoria')).show();
  }

  async function guardarCategoria() {
    const id = document.getElementById('catIdInput').value;
    const payload = {
      nombre: document.getElementById('catNombreInput').value.trim(),
      descripcion: document.getElementById('catDescInput').value.trim()
    };
    const url = id ? `/api/admin/categorias/${id}/` : '/api/admin/categorias/';
    const method = id ? 'PUT' : 'POST';
    const res = await apiFetch(url, { method, body: JSON.stringify(payload) });
    if (!res.ok) {
      window.mostrarToast(res.data?.error || 'Error al guardar la categoría.', 'error');
      return;
    }
    bootstrap.Modal.getInstance(document.getElementById('modalCategoria'))?.hide();
    window.mostrarToast(`Categoría "${res.data.nombre}" guardada correctamente.`, 'success');
    cargarCategorias();
  }

  // ---------- Marcas CRUD ----------
  async function cargarMarcas() {
    const res = await apiFetch('/api/admin/marcas/');
    if (!res.ok || !res.data) return;
    marcasLista = res.data.results || [];
    document.getElementById('navBadgeMarcas').textContent = marcasLista.length;

    const tbody = document.getElementById('tablaMarcasAdminBody');
    if (!tbody) return;
    if (!marcasLista.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-secondary">No hay marcas registradas.</td></tr>';
      return;
    }

    tbody.innerHTML = marcasLista.map(m => `
      <tr>
        <td class="text-muted small">#${m.id}</td>
        <td class="fw-bold">${escapeHtml(m.nombre)}</td>
        <td class="small text-secondary"><i class="bi bi-globe-americas me-1 text-primary"></i>${escapeHtml(m.pais_origen || 'No especificado')}</td>
        <td class="text-center"><span class="badge badge-soft-indigo rounded-pill px-3">${m.total_productos || 0}</span></td>
        <td class="text-end text-nowrap">
          <button type="button" class="btn btn-sm btn-outline-primary py-1 px-2 me-1" onclick="AdminApp.abrirModalMarca(${m.id})">
            <i class="bi bi-pencil-square"></i>
          </button>
          <button type="button" class="btn btn-sm btn-outline-danger py-1 px-2" onclick="AdminApp.confirmarEliminar('marca', ${m.id}, '${escapeHtml(m.nombre)}')">
            <i class="bi bi-trash3"></i>
          </button>
        </td>
      </tr>
    `).join('');
  }

  function abrirModalMarca(id = null) {
    if (id) {
      const m = marcasLista.find(x => x.id === id);
      if (!m) return;
      document.getElementById('modalMarcaTitle').textContent = `Editar Marca #${m.id}`;
      document.getElementById('marcaIdInput').value = m.id;
      document.getElementById('marcaNombreInput').value = m.nombre;
      document.getElementById('marcaPaisInput').value = m.pais_origen || '';
    } else {
      document.getElementById('modalMarcaTitle').textContent = 'Nueva Marca';
      document.getElementById('marcaIdInput').value = '';
      document.getElementById('marcaNombreInput').value = '';
      document.getElementById('marcaPaisInput').value = '';
    }
    bootstrap.Modal.getOrCreateInstance(document.getElementById('modalMarca')).show();
  }

  async function guardarMarca() {
    const id = document.getElementById('marcaIdInput').value;
    const payload = {
      nombre: document.getElementById('marcaNombreInput').value.trim(),
      pais_origen: document.getElementById('marcaPaisInput').value.trim()
    };
    const url = id ? `/api/admin/marcas/${id}/` : '/api/admin/marcas/';
    const method = id ? 'PUT' : 'POST';
    const res = await apiFetch(url, { method, body: JSON.stringify(payload) });
    if (!res.ok) {
      window.mostrarToast(res.data?.error || 'Error al guardar la marca.', 'error');
      return;
    }
    bootstrap.Modal.getInstance(document.getElementById('modalMarca'))?.hide();
    window.mostrarToast(`Marca "${res.data.nombre}" guardada correctamente.`, 'success');
    cargarMarcas();
  }

  // ===================================================================
  // D) GESTIÓN DE USUARIOS Y CONFIGURACIÓN
  // ===================================================================
  async function cargarUsuarios() {
    const params = new URLSearchParams();
    const q = (document.getElementById('userBuscarInput')?.value || '').trim();
    const rol = document.getElementById('userFiltroRol')?.value || '';
    if (q) params.set('q', q);
    if (rol) params.set('rol', rol);

    const res = await apiFetch(`/api/admin/usuarios/?${params.toString()}`);
    if (!res.ok || !res.data) return;
    usuariosLista = res.data.results || [];
    document.getElementById('navBadgeUsuarios').textContent = usuariosLista.length;

    const tbody = document.getElementById('tablaUsuariosAdminBody');
    if (!tbody) return;
    if (!usuariosLista.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-secondary">No se encontraron usuarios.</td></tr>';
      return;
    }

    tbody.innerHTML = usuariosLista.map(u => {
      const badgeRol = u.rol === 'superuser'
        ? '<span class="badge badge-soft-primary rounded-pill"><i class="bi bi-shield-check me-1"></i>Superusuario</span>'
        : u.rol === 'staff'
          ? '<span class="badge badge-soft-info rounded-pill"><i class="bi bi-person-badge me-1"></i>Staff</span>'
          : '<span class="badge bg-secondary-subtle text-secondary rounded-pill">Cliente</span>';

      const badgeActivo = u.is_active
        ? '<span class="badge badge-soft-success rounded-pill">Activo</span>'
        : '<span class="badge badge-soft-danger rounded-pill">Inactivo</span>';

      return `
        <tr>
          <td class="fw-bold"><i class="bi bi-person-circle text-primary me-1"></i>${escapeHtml(u.username)}</td>
          <td>${escapeHtml(u.nombre_completo)}</td>
          <td class="small text-secondary">${escapeHtml(u.email || '—')}</td>
          <td>${badgeRol}</td>
          <td>${badgeActivo}</td>
          <td class="small text-muted">${escapeHtml(u.date_joined)}</td>
          <td class="text-end text-nowrap">
            <button type="button" class="btn btn-sm btn-outline-primary py-1 px-2 me-1" onclick="AdminApp.abrirModalUsuario(${u.id})">
              <i class="bi bi-pencil-square"></i>
            </button>
            <button type="button" class="btn btn-sm btn-outline-danger py-1 px-2" onclick="AdminApp.confirmarEliminar('usuario', ${u.id}, '${escapeHtml(u.username)}')">
              <i class="bi bi-trash3"></i>
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  function abrirModalUsuario(id = null) {
    const pwdInput = document.getElementById('userPasswordInput');
    const pwdLabel = document.getElementById('userPasswordLabel');
    if (id) {
      const u = usuariosLista.find(x => x.id === id);
      if (!u) return;
      document.getElementById('modalUsuarioTitle').textContent = `Editar Usuario: ${u.username}`;
      document.getElementById('userIdInput').value = u.id;
      document.getElementById('userUsernameInput').value = u.username;
      document.getElementById('userRolInput').value = u.rol;
      document.getElementById('userFirstNameInput').value = u.first_name || '';
      document.getElementById('userLastNameInput').value = u.last_name || '';
      document.getElementById('userEmailInput').value = u.email || '';
      document.getElementById('userActiveCheck').checked = u.is_active;
      pwdInput.value = '';
      pwdInput.required = false;
      pwdInput.placeholder = 'Dejar en blanco para mantener actual';
      pwdLabel.textContent = 'Nueva Contraseña (opcional)';
    } else {
      document.getElementById('modalUsuarioTitle').textContent = 'Nuevo Usuario / Cliente';
      document.getElementById('userIdInput').value = '';
      document.getElementById('userUsernameInput').value = '';
      document.getElementById('userRolInput').value = 'cliente';
      document.getElementById('userFirstNameInput').value = '';
      document.getElementById('userLastNameInput').value = '';
      document.getElementById('userEmailInput').value = '';
      document.getElementById('userActiveCheck').checked = true;
      pwdInput.value = '';
      pwdInput.required = true;
      pwdInput.placeholder = 'Mínimo 6 caracteres';
      pwdLabel.textContent = 'Contraseña *';
    }
    bootstrap.Modal.getOrCreateInstance(document.getElementById('modalUsuario')).show();
  }

  async function guardarUsuario() {
    const id = document.getElementById('userIdInput').value;
    const payload = {
      username: document.getElementById('userUsernameInput').value.trim(),
      rol: document.getElementById('userRolInput').value,
      first_name: document.getElementById('userFirstNameInput').value.trim(),
      last_name: document.getElementById('userLastNameInput').value.trim(),
      email: document.getElementById('userEmailInput').value.trim(),
      is_active: document.getElementById('userActiveCheck').checked
    };
    const pwd = document.getElementById('userPasswordInput').value.trim();
    if (pwd) payload.password = pwd;

    const url = id ? `/api/admin/usuarios/${id}/` : '/api/admin/usuarios/';
    const method = id ? 'PUT' : 'POST';
    const res = await apiFetch(url, { method, body: JSON.stringify(payload) });
    if (!res.ok) {
      window.mostrarToast(res.data?.error || 'Error al guardar el usuario.', 'error');
      return;
    }
    bootstrap.Modal.getInstance(document.getElementById('modalUsuario'))?.hide();
    window.mostrarToast(`Usuario "${res.data.username}" guardado con éxito.`, 'success');
    cargarUsuarios();
  }

  async function guardarConfiguracion() {
    const payload = {
      nombre_tienda: document.getElementById('cfgNombre').value.trim(),
      email_contacto: document.getElementById('cfgEmail').value.trim(),
      slogan: document.getElementById('cfgSlogan').value.trim(),
      telefono_contacto: document.getElementById('cfgTelefono').value.trim(),
      direccion: document.getElementById('cfgDireccion').value.trim(),
      horario_atencion: document.getElementById('cfgHorario').value.trim(),
      iva_porcentaje: Number(document.getElementById('cfgIva').value),
      stock_minimo_alerta: Number(document.getElementById('cfgStockMin').value),
      envio_gratis_desde: Number(document.getElementById('cfgEnvioGratis').value)
    };

    const res = await apiFetch('/api/admin/configuracion/', {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      window.mostrarToast(res.data?.error || 'Error al actualizar la configuración.', 'error');
      return;
    }
    window.mostrarToast('Configuración general actualizada correctamente.', 'success');
  }

  // ===================================================================
  // MODAL DE CONFIRMACIÓN DE ELIMINACIÓN
  // ===================================================================
  function confirmarEliminar(tipo, id, nombre) {
    const textoEl = document.getElementById('confirmarEliminarTexto');
    const btnAccion = document.getElementById('btnConfirmarEliminarAccion');
    textoEl.innerHTML = `Estás a punto de eliminar <strong>${escapeHtml(nombre)}</strong>. Esta acción es permanente.`;

    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('modalConfirmarEliminar'));
    btnAccion.onclick = async function () {
      const endpoints = {
        producto: `/api/admin/productos/${id}/`,
        categoria: `/api/admin/categorias/${id}/`,
        marca: `/api/admin/marcas/${id}/`,
        venta: `/api/admin/ventas/${id}/`,
        usuario: `/api/admin/usuarios/${id}/`
      };
      const res = await apiFetch(endpoints[tipo], { method: 'DELETE' });
      modal.hide();
      if (!res.ok) {
        window.mostrarToast(res.data?.error || 'No fue posible eliminar el registro.', 'error');
        return;
      }
      window.mostrarToast(`"${nombre}" fue eliminado correctamente.`, 'success');
      if (tipo === 'producto') cargarProductos();
      if (tipo === 'categoria') cargarCategorias();
      if (tipo === 'marca') cargarMarcas();
      if (tipo === 'venta') cargarVentas();
      if (tipo === 'usuario') cargarUsuarios();
      cargarMetricasDashboard(false);
    };
    modal.show();
  }

  // ===================================================================
  // INICIALIZACIÓN Y EVENTOS
  // ===================================================================
  function init() {
    // Botones del sidebar
    document.querySelectorAll('.admin-nav-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        cambiarSeccion(btn.getAttribute('data-section'));
      });
    });

    // Botones de período y tipo de gráfico
    document.querySelectorAll('[data-chart-period]').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('[data-chart-period]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        chartPeriodoActual = btn.getAttribute('data-chart-period');
        renderizarGraficoPeriodo();
      });
    });

    document.querySelectorAll('[data-chart-type]').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('[data-chart-type]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        chartTipoActual = btn.getAttribute('data-chart-type');
        renderizarGraficoPeriodo();
      });
    });

    // Redibujar gráficos al cambiar modo oscuro/claro
    window.addEventListener('themeChanged', () => {
      renderizarGraficoPeriodo();
      renderizarGraficoCategorias();
    });

    // Eventos de filtrado en tiempo real para Productos
    let prodSearchTimer = null;
    document.getElementById('prodBuscarInput')?.addEventListener('input', () => {
      clearTimeout(prodSearchTimer);
      prodSearchTimer = setTimeout(cargarProductos, 220);
    });
    ['prodFiltroCat', 'prodFiltroEspecie', 'prodFiltroStock', 'prodOrdenSelect'].forEach(id => {
      document.getElementById(id)?.addEventListener('change', cargarProductos);
    });
    document.getElementById('prodPageSize')?.addEventListener('change', e => {
      prodPorPagina = Number(e.target.value) || 10;
      prodPaginaActual = 1;
      renderizarTablaProductos();
    });

    // Búsqueda rápida en Usuarios
    document.getElementById('userBuscarInput')?.addEventListener('input', () => {
      clearTimeout(prodSearchTimer);
      prodSearchTimer = setTimeout(cargarUsuarios, 250);
    });
    document.getElementById('userFiltroRol')?.addEventListener('change', cargarUsuarios);

    // Cargar sección inicial
    const secInicial = window.INITIAL_ADMIN_SECTION || 'dashboard';
    cambiarSeccion(secInicial);
  }

  document.addEventListener('DOMContentLoaded', init);

  return {
    cambiarSeccion,
    cargarMetricasDashboard,
    cargarVentas,
    filtrarPeriodoVentas,
    limpiarFiltrosVentas,
    exportarVentasCSV,
    cambiarEstadoVenta,
    verDetalleVenta,
    abrirModalNuevaVenta,
    agregarLineaVenta,
    recalcularTotalesPOS,
    guardarNuevaVenta,
    cargarProductos,
    irPaginaProductos,
    cambiarOrdenProductos,
    ajustarStockRapido,
    abrirModalProducto,
    guardarProducto,
    cargarCategorias,
    abrirModalCategoria,
    guardarCategoria,
    cargarMarcas,
    abrirModalMarca,
    guardarMarca,
    cargarUsuarios,
    abrirModalUsuario,
    guardarUsuario,
    guardarConfiguracion,
    confirmarEliminar
  };
})();

