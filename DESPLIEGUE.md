# Despliegue · Operatividad Control Center

## 1. Con qué está construido

| Capa | Tecnología |
|---|---|
| Aplicación | **Python 3.11+ · Streamlit** (`app.py`) |
| Datos | pandas · numpy · pyarrow (caché en parquet) |
| Lectura del Excel | openpyxl + lector propio de *pivot cache* (`core/pivotcache.py`) |
| Gráficos | Plotly |
| Exportación | XlsxWriter |
| Conexión al maestro | requests (descarga directa) o ruta sincronizada |
| Configuración | `config/schema.yml` + `.streamlit/secrets.toml` |

No hay base de datos ni backend aparte: es una sola aplicación Streamlit.

---

## 2. Levantar en local

```bash
pip install -r requirements.txt
```

```bash
streamlit run app.py
```

Abre en `http://localhost:8501`. En Windows también funciona `run.bat`.

**Primera carga:** procesar el Excel toma ~30 s. El resultado queda en caché
(`%LOCALAPPDATA%\OperatividadEcommerce\cache`), así que las siguientes aperturas
son inmediatas.

---

## 3. Variables y secretos

Copie `.streamlit/secrets.example.toml` a `.streamlit/secrets.toml`:

```toml
[app_auth]
username = "hugo.camara@forus.pe"
password = "UNA_CLAVE_LARGA"

[datasource]
modo = "local"
ruta = "C:/Users/hcamara/OneDrive - Peru Forus S.A/Operacion/BD Operacion Ecommerce.xlsx"
refrescar_cada_min = 60
```

Equivalentes por variable de entorno (útiles en hosting): `OPS_USER`,
`OPS_PASSWORD`, `OPS_MASTER_PATH`, `OPS_MASTER_URL`.

> Si no define `[app_auth]`, la aplicación queda **abierta**. Configúrelo siempre
> antes de publicarla.

---

## 4. Qué fuente de datos usar

La aplicación resuelve el origen en este orden:

1. **BigQuery** — si `[bigquery].enabled = true` y las consultas responden.
2. **Excel maestro** — modo `local` o `url`.
3. **Carga manual** — siempre disponible como respaldo.

Si BigQuery falla (sin librería, sin credenciales, consulta con error o
faltan columnas críticas), la app **cae sola al Excel** y lo avisa en la
pestaña Fuente. Nunca se queda sin datos por ese motivo.

### Modos del Excel

La aplicación soporta tres modos y **no** hay que elegir uno solo: el manual
siempre queda como respaldo.

| Escenario | Modo recomendado | Por qué |
|---|---|---|
| El equipo usa la app en su PC | **`local`** sobre la carpeta de OneDrive | OneDrive ya sincroniza el archivo; la app sólo mira la fecha de modificación. Sin credenciales, sin API, sin cuotas. **Es la opción más simple y la más rápida.** |
| App publicada en la nube | **`url`** con enlace de SharePoint/OneDrive | El servidor no tiene la carpeta montada; necesita descargarlo por HTTPS. |
| Carga puntual o corrección | **`upload`** | Reemplaza la fuente sólo en esa sesión. |

### Enlace para el modo `url`

1. En OneDrive/SharePoint: **Compartir → Copiar vínculo**.
2. Permiso: *Cualquier persona con el vínculo* (o *Personas de Forus*, si el
   hosting está dentro del tenant).
3. Pegue el enlace tal cual en `url`. La app lo convierte a descarga directa
   sola (SharePoint, OneDrive personal y Google Drive).

Si el tenant obliga a iniciar sesión, el enlace anónimo no funcionará. En ese
caso use el modo `local` en un equipo con OneDrive sincronizado, o publique el
archivo en un almacenamiento con URL directa (Azure Blob con SAS, S3 firmado).

---

## 5. Subir a GitHub

```bash
git init
git add .
git commit -m "Operatividad Control Center"
git branch -M main
git remote add origin https://github.com/USUARIO/operatividad-control-center.git
git push -u origin main
```

El `.gitignore` ya excluye `secrets.toml`, los `.xlsx` y la caché.
**Use un repositorio privado**: aunque los secretos no se suban, el esquema
describe la operación interna.

---

## 6. Publicar para que otros entren por URL

**Streamlit Community Cloud no es la única forma.** La app es un proceso web
Python normal: corre en cualquier sitio que ejecute un contenedor o un proceso
de larga duración. Lo único que **no** sirve es un hosting estático (GitHub
Pages, Netlify) o funciones serverless con timeout corto, porque Streamlit
mantiene una sesión WebSocket abierta.

| Opción | Costo | Esfuerzo | Cuándo conviene |
|---|---|---|---|
| **Streamlit Community Cloud** | Gratis | Muy bajo | Publicar hoy mismo. Repo en GitHub, secrets pegados en el panel. |
| **Azure App Service / Container Apps** | Pago | Medio | **La mejor opción para Forus**: el tenant ya es Microsoft, permite login corporativo (Entra ID) delante de la app y leer SharePoint con identidad administrada, sin enlaces anónimos. |
| **Google Cloud Run** | Pago por uso | Medio | Escala a cero. Natural si los datos vienen de BigQuery. |
| **Render · Railway · Fly.io** | Gratis/bajo | Bajo | Alternativa sencilla a Streamlit Cloud, con más control. |
| **Servidor interno (IIS/nginx como reverse proxy)** | Infra propia | Alto | Si el dato no puede salir de la red de Forus. |
| **Docker en cualquier VM** | Variable | Medio | Control total; el `Dockerfile` de abajo sirve para todos. |

### A · Streamlit Community Cloud

1. Entre a <https://share.streamlit.io> con la cuenta de GitHub.
2. **New app** → repositorio y rama `main`.
3. **Main file path**: `app.py`.
4. **Advanced settings → Secrets**: pegue su `secrets.toml`
   (con `modo = "url"`, porque el servidor no ve su disco).
5. Deploy → `https://operatividad-control-center.streamlit.app`.

### B · Azure App Service (recomendada para el entorno Forus)

```bash
az webapp up --runtime "PYTHON:3.11" --sku B1 --name operatividad-cc
az webapp config set --name operatividad-cc \n  --startup-file "python -m streamlit run app.py --server.port 8000 --server.address 0.0.0.0"
```

Los secrets se cargan como *App settings* (`OPS_USER`, `OPS_PASSWORD`,
`OPS_MASTER_URL`). Active **Authentication → Microsoft** para poner Entra ID
delante y **Always On** para evitar el arranque en frío.

### C · Contenedor (Cloud Run, Render, Fly.io, VM propia)

`Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["streamlit", "run", "app.py", \n     "--server.port=8080", "--server.address=0.0.0.0", "--server.headless=true"]
```

```bash
gcloud run deploy operatividad-cc --source . --allow-unauthenticated --region us-central1
```

### Comando genérico para cualquier hosting

```bash
streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true
```

---

## 7. Mantenerlo encendido

- **Streamlit Community Cloud** duerme la app tras ~7 días sin visitas y la
  despierta sola en la siguiente. Para uso diario no se nota.
- **Azure / Cloud Run**: active *Always On* (Azure) o un mínimo de 1 instancia
  (Cloud Run) si quiere evitar el arranque en frío.
- La caché en parquet hace que el arranque tras dormir sea de segundos, no de
  medio minuto.

---

## 8. Actualizar el Excel sin volver a desplegar

Este es el punto importante: **el código y los datos están separados**.

1. Guarde el Excel actualizado en la misma ruta o en el mismo enlace.
2. La aplicación detecta el cambio por fecha de modificación (modo `local`) o
   por `ETag`/`Last-Modified` (modo `url`).
3. En la pestaña **🔌 Fuente**, pulse **Actualizar ahora** — o simplemente
   recargue: la comprobación es automática.

Nunca hace falta un redeploy para cambiar datos. Sólo se redespliega cuando
cambia el código o los alias de `config/schema.yml`.

### Si cambia un encabezado del Excel

Las columnas se leen **por nombre, nunca por posición**, y el emparejamiento
tolera mayúsculas, tildes, espacios y guiones bajos. Si un encabezado cambia por
completo, añádalo a `aliases` en `config/schema.yml`:

```yaml
total: {required: true, type: float,
        aliases: ["Total", "Monto Total", "Total con IGV", "NOMBRE NUEVO"]}
```

Si falta una columna **crítica**, la app no se rompe: indica exactamente cuál
falta y en qué conjunto.

---

## 9. Comprobaciones

```bash
python tests/test_esquema.py
```

```bash
python tests/test_comparativos.py
```

```bash
python tests/test_secciones.py
```

```bash
python tests/test_bigquery.py
```
