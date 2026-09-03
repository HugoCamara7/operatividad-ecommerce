# Operatividad Control Center

Centro de control de la operación ecommerce (Forus Perú).

**Despliegue y puesta en marcha:** [DESPLIEGUE.md](DESPLIEGUE.md)

---

## Cómo se ejecuta

```bash
pip install -r requirements.txt
```

```bash
streamlit run app.py
```

En Windows también sirve hacer doble clic en `run.bat`.

---

## Cómo se actualiza con un Excel nuevo

La aplicación se **conecta sola** al Excel maestro; no hace falta subirlo cada vez.

1. Guarde el archivo actualizado en la ruta o el enlace configurado.
2. La app detecta el cambio (fecha de modificación o `ETag`).
3. En la pestaña **🔌 Fuente**, pulse **Actualizar ahora** si quiere forzarlo.

La carga manual sigue disponible como respaldo en esa misma pestaña.
Configuración en `.streamlit/secrets.toml` — vea
[`secrets.example.toml`](.streamlit/secrets.example.toml).

El procesamiento del archivo completo toma unos 25–30 segundos. El resultado
queda guardado, de modo que volver a abrir el mismo archivo es instantáneo.

### Si cambia el nombre de una columna

Las columnas se leen **siempre por nombre, nunca por posición**, y el
emparejamiento ya tolera diferencias de mayúsculas, tildes, espacios y guiones
bajos (`SKU`, `Sku`, `sku `, `S.K.U.` son la misma columna).

Si un encabezado cambia por completo, basta con añadirlo a la lista de `aliases`
del campo correspondiente en [`config/schema.yml`](config/schema.yml).
No hay que tocar el código.

```yaml
total: {required: true, type: float,
        aliases: ["Total", "Monto Total", "Total con IGV", "SU NOMBRE NUEVO"]}
```

Si falta una columna **crítica**, la aplicación no se rompe: indica exactamente
cuál falta y en qué conjunto de datos.

---

## De dónde salen los datos

El libro no es una base de datos: sus nueve hojas son tablas dinámicas ya
calculadas. El detalle registro a registro vive en los **pivot caches** del
archivo, porque las hojas de origen (`2026`, `ForusApp 2`, `Urbano`, `Tabla1`)
están en libros externos. La aplicación lee esos caches directamente.

| Conjunto | Origen | Registros | Contenido |
|---|---|---|---|
| **Órdenes** | hoja `2026` | 112 044 líneas · 66 408 pedidos | Venta, SKU, tienda, estado, pago, geografía |
| **OTIF** | hoja `ForusApp 2` | 5 684 líneas | On-Time, In-Full, tiempos y responsable de la demora |
| **Carrier** | hoja `Urbano` | 3 501 envíos | Tracking, SLA vs. real, visitas, estados |
| **Quiebres** | hoja `Tabla1` | 138 | Quiebre de stock, monto perdido, días de gestión |

Los cuatro conjuntos se cruzan por `Order`. Cada uno se reconoce por sus
**columnas firma**, no por el nombre de la hoja ni por el orden, así que la
identificación sobrevive a cambios de estructura.

También sirve el **consolidado plano** —una hoja normal, un registro por fila—
en lugar del libro de tablas dinámicas: se reconoce igual por sus columnas
firma, y el encabezado se busca en las primeras filas, de modo que un título o
una fila en blanco encima de los nombres de columna no estorban.

> Las bases de OTIF, carrier y quiebres cubren un rango de fechas más corto que
> el maestro de pedidos. Al filtrar períodos anteriores esas secciones aparecen
> vacías: es el dato, no un error.

---

## Cómo se cuenta

Estas convenciones vienen de la estructura real del archivo y evitan inflar las
cifras:

- **Las filas son líneas de pedido, no pedidos.** Los conteos de pedidos usan
  valores únicos de `Order`; los montos se suman a nivel línea.
- **`Duplicado = 1`** marca la línea que se debe contar. El interruptor *Sólo
  líneas únicas* aplica ese criterio.
- **`# Ordenes`** es el peso `1/n` que reparte un pedido entre sus líneas.
- La **venta** excluye los pedidos cancelados; el monto de los cancelados se
  reporta aparte como *venta perdida*.

---

## Arquitectura

Cada capa está separada para que el Excel pueda reemplazarse por una conexión
directa sin rehacer el dashboard.

```
app.py                  Punto de entrada: acceso, cabecera, filtros y ruteo
requirements.txt
.streamlit/
  config.toml            Tema de Streamlit
  secrets.example.toml   Plantilla de credenciales y fuente de datos
config/
  schema.yml             Aliases, normalización de valores y umbrales
core/                    Lógica de datos (sin nada de interfaz)
  pivotcache.py          Lectura de los pivot caches del .xlsx
  sources.py             Orígenes de datos (Excel, SQL)
  bigquery.py            Origen directo opcional
  master.py              Conexión al Excel maestro y su estado
  normalize.py           Nombres de columna y validación de estructura
  clean.py               Tipos, mojibake, valores nulos y variantes
  transform.py           Modelo canónico y campos derivados
  kpis.py                Cálculo de indicadores
  compare.py             Períodos y variaciones
  filters.py             Estado de filtros y su aplicación
  repository.py          Caché en parquet de las cargas procesadas
  export.py              Generación del Excel y del CSV
  auth.py                Acceso por usuario y contraseña
ui/                      Interfaz (sin nada de lógica de datos)
  theme.py               Paleta y hoja de estilos
  components.py          Tarjetas KPI, paneles, tablas
  charts.py              Constructores de gráficos
  blocks.py              Preparación de datos de cada sección
  report.py              Las seis secciones
  login.py               Pantalla de acceso
  helpers.py             Contexto compartido
  pages/                 Detalle y fuente de datos
tests/                   Pruebas de esquema, comparativos e integración
```

### Conectar una base de datos más adelante

Toda la aplicación consume el contrato `DataSource` de
[`core/sources.py`](core/sources.py), con dos operaciones: `headers()`
para descubrir qué hay y `load()` para traerlo. La clase `SQLSource` ya está
esbozada: al completar las consultas, el resto del dashboard —normalización,
KPIs, filtros, gráficos e interfaz— sigue funcionando sin cambios.

---

## Secciones

| Sección | Responde a |
|---|---|
| **◧ Resumen** | Estado del negocio en una pantalla: venta, órdenes, embudo y cumplimiento |
| **⚙ Operatividad** | Pedidos, documentación, OTIF, modalidad y tipo de entrega (MW/Regular/ND/SD) y operador logístico |
| **🏬 Tiendas** | Ranking, concentración, volumen frente a cancelación y flujo por tienda |
| **🔖 Productos** | Qué se vende, por marca, y quiebres de stock |
| **⇄ Comparativos** | Actual vs. referencia por indicador, mes y dimensión |
| **▤ Detalle** | Tabla filtrable con búsqueda y exportación a Excel/CSV |
| **🔌 Fuente** | Conexión al maestro, validación, mapeo de columnas y calidad |

Cada indicador se muestra con **valor actual, referencia, diferencia y
variación %**. La referencia se elige en la barra de filtros: período anterior,
mismo período del año anterior o un rango personalizado.

Los umbrales de los semáforos se configuran en la sección `business.semaforos`
de `schema.yml` (meta de OTIF: **97 %**).

### Filtro de fechas

Los atajos de período (**Últimos 7/30/90 días**, **Mes del último dato**, …) se
cuentan desde el **último día con datos del archivo**, no desde la fecha de hoy:
el maestro siempre va unos días atrasado y, si se contaran desde hoy, el rango
saldría vacío. Sólo se ofrecen los atajos que de verdad recortan el archivo
cargado: sobre un archivo de 26 días no aparecen «últimos 30» ni «mes anterior».

Cuando la ventana de comparación cae fuera de lo que el archivo trae, la
pastilla de referencia y la cabecera de sección lo dicen (*sin datos* o
*cobertura parcial*): comparar contra días que no existen produce variaciones
de +600 % que no significan nada.

Al cargar un archivo nuevo, el rango de fechas vuelve a su valor inicial sobre
las fechas del archivo recién subido.

---

## Problemas de datos que la aplicación corrige

Detectados en el archivo y resueltos en la capa de limpieza:

- **Mojibake** por doble codificación UTF-8 (`MarrÃ³n` → `Marrón`).
- **`Cuzco` / `Cusco`** eran el mismo departamento contado por separado.
- **Marcas** inconsistentes (`VANS`, `PARFOIS`, `Hushpuppies`).
- **Operador** `Sharff` / `Scharf`.
- **Vocabularios distintos entre bases**: OTIF identifica el sitio como
  `columbiaperu` y el maestro como `Columbia`; el carrier entrega los
  departamentos en mayúsculas. Se alinean para que un filtro afecte a todas.
- **Estados escritos en la columna de tienda** en la base de quiebres
  (`Cancelada manual` aparecía como la tienda con más quiebres).
- Marcadores de vacío (`-`, `(en blanco)`) tratados como nulos.

Quedan señalados en la sección **Datos**, sin corregir, por ser propios del
negocio: montos negativos (devoluciones), líneas con `Total sin IGV = 0`, y el
último mes incompleto.

### Datos personales

El archivo trae correo, documento, dirección y teléfono. Por defecto se cargan
**enmascarados** (`e•••@dominio.com`). El comportamiento se controla con el
parámetro `mask_pii` de `build_model()`.

---

## Pruebas

```bash
python tests/test_esquema.py
```

Comprueba que los encabezados se emparejen pese a variaciones, que los alias
alternativos funcionen, que las columnas nuevas se ignoren y —lo más
importante— que **una columna crítica ausente se reporte por su nombre en lugar
de romper la aplicación**.

```bash
python tests/test_integracion.py
```

Recorre la carga real, ocho combinaciones de filtros, los doce tipos de gráfico
y la exportación.
