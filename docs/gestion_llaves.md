# Gestión de llaves criptográficas — CostFlow

## 1. Propósito

CostFlow utiliza dos llaves principales:

* `SECRET_KEY`: utilizada por Flask para firmar y proteger información asociada a las sesiones.
* `MASTER_ENCRYPTION_KEY`: llave maestra de la que `CryptoService` deriva las llaves usadas para cifrar datos sensibles.

Ambas son secretos de la aplicación: deben mantenerse fuera del código fuente y del repositorio, y proporcionarse mediante variables de entorno. Actualmente CostFlow usa archivos `.env` como mecanismo de almacenamiento.

---

## 2. Referencia rápida ante un compromiso

Si sospechas que una llave, token o credencial fue expuesta, esta tabla resume la respuesta. El detalle completo está en la sección 9.

| Se compromete | ¿Se regenera solo? | Acción |
|---|---|---|
| `SECRET_KEY` | Sí | Generar nueva llave (§4) → reiniciar → sesiones existentes quedan invalidadas automáticamente |
| Token de sesión | Sí | Invalidar el token → generar uno nuevo con la credencial de API vigente |
| `MASTER_ENCRYPTION_KEY` | Depende del dato cifrado | Generar nueva llave (§4) → clasificar cada valor cifrado como regenerable o no (§5) → versionar solo si algo no regenerable debe conservarse (§8) |
| Credencial de API | **No** — requiere al proveedor | Revocarla en el proveedor → generar una nueva ahí → registrarla en CostFlow → invalidar y regenerar los tokens de sesión que dependían de ella |

Regla general: **rotar una llave interna nunca es, por sí sola, la recuperación completa.** Si el material expuesto incluye credenciales de proveedores externos, esas credenciales deben revocarse en el proveedor, no solo re-cifrarse con una llave nueva.

---

## 3. Llaves utilizadas por la aplicación

### 3.1 SECRET_KEY

Usada por Flask para las operaciones criptográficas de sesión.

```env
SECRET_KEY=1379b9be2395a528b317931aa7a1676904d9225bb4d38b50096c9416e3501bbd
```

*(valor de ejemplo — no usar en producción)*

### 3.2 MASTER_ENCRYPTION_KEY

Llave raíz usada para derivar las llaves específicas de `CryptoService`. **No se usa directamente como llave Fernet.**

```env
MASTER_ENCRYPTION_KEY=ucA-v4xUOc6r0BP1CdMwIssBKrphbYwPBT8r2P2UbtQ
```

La aplicación espera que esta llave:

* esté codificada en Base64 URL-safe;
* represente como mínimo 32 bytes;
* sea generada mediante un generador criptográficamente seguro.

---

## 4. Generación de llaves

```bash
# SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# MASTER_ENCRYPTION_KEY
python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode())"
```

No debe modificarse manualmente una llave después de generarla.

---

## 5. Naturaleza de los secretos cifrados

Los valores protegidos con `MASTER_ENCRYPTION_KEY` caen en dos categorías con comportamiento distinto ante un compromiso:

| | Credenciales de API | Tokens de sesión |
|---|---|---|
| **Origen** | Emitidas por el proveedor externo (Stripe, etc.) | Derivadas de una credencial de API válida |
| **¿CostFlow puede regenerarlas sola?** | No — depende del proveedor | Sí, mientras la credencial de API siga siendo válida |
| **Ante sospecha de compromiso** | Revocar en el proveedor, generar nueva, re-registrar en CostFlow | Invalidar y regenerar; no es necesario conservarlas |

Si hay evidencia de acceso no autorizado a la base de datos o a las llaves de cifrado, debe asumirse que **también** las credenciales originales de API pudieron quedar expuestas, aunque estuvieran cifradas correctamente.

---

## 6. Almacenamiento

Variables requeridas:

```env
SECRET_KEY=<secret-key>
MASTER_ENCRYPTION_KEY=<master-key>
```

`.gitignore`:

```gitignore
.env
.env.*
!.env.example
```

`.env.example` documenta las variables sin valores reales.

**Protección del `.env`:** no subir a Git, no compartir, no incluir en documentación, imágenes Docker, logs o capturas de pantalla. En Linux:

```bash
chmod 600 .env
```

**Sobre backups de `MASTER_ENCRYPTION_KEY`:** deliberadamente no se mantiene backup de esta llave. Si se pierde, no representa pérdida permanente de datos: las credenciales de proveedores se vuelven a registrar y los tokens de sesión se regeneran automáticamente. Mantener una copia de respaldo añadiría otra copia del secreto en circulación sin un beneficio que lo justifique, dado que nada de lo cifrado es irrecuperable por otra vía.

**Separación de ambientes:** cada ambiente (desarrollo, producción) tiene su propio `.env` con sus propias llaves. Las llaves de producción nunca se copian a desarrollo.

**Futuro:** si se incorpora un gestor de secretos externo, esta documentación deberá actualizarse. Hasta entonces, `.env` es el mecanismo oficial.

---

## 7. Funcionamiento de MASTER_ENCRYPTION_KEY (HKDF)

```text
MASTER_ENCRYPTION_KEY
        │
        ▼
Base64 URL-safe decode → master key en bytes
        │
        ▼
        HKDF-SHA256
        │
        ├── info = "credentials" → llave derivada → Fernet
        └── info = "sessions"    → llave derivada → Fernet
```

```python
salt = hashlib.sha256(b"CostFlow").digest()
_PURPOSE_CREDENTIALS = b"credentials"
_PURPOSE_SESSIONS = b"sessions"
```

**Sobre el salt fijo:** el `salt` usado en HKDF es constante (`SHA256("CostFlow")`) en lugar de aleatorio por instalación o por valor cifrado. Esto es intencional y no compromete la seguridad del esquema: en HKDF el salt no necesita mantenerse en secreto ni ser único — su función es aportar dominio de separación, no aleatoriedad de entropía. Toda la seguridad de la derivación recae en el secreto de `MASTER_ENCRYPTION_KEY`, no en el salt. Lo que sí aporta separación entre propósitos (`credentials` vs. `sessions`) es el parámetro `info`, que es distinto para cada uno — eso es lo que garantiza que ambas llaves derivadas sean independientes entre sí aunque compartan el mismo salt y la misma master key.

Si en el futuro se quisiera introducir un salt distinto por instalación, sería un cambio incompatible hacia atrás: los datos ya cifrados no podrían descifrarse sin conocer también el salt original usado para cada uno. Cualquier cambio de este tipo debería ir acompañado de un nuevo valor de `_KEY_VERSION` (§8) y no reemplazar el esquema actual en caliente.

---

## 8. Versionamiento de llaves

Los valores cifrados incluyen la versión de la llave usada:

```text
v1:gAAAAAB...
```

```python
_KEY_VERSION = "v1"
_LEGACY_MASTER_KEYS: dict[str, bytes] = {}
```

La versión **no es secreta**; la master key asociada a ella sí lo es.

**Llaves históricas — estado real en código:** `_LEGACY_MASTER_KEYS` es un diccionario de clase que hoy está vacío por defecto (`{}`). `CryptoService` sabe *leer* de ahí una master key por versión (`_master_key_for_version`), pero **no incluye ningún mecanismo para poblarlo** — ni automático desde variables de entorno tipo `MASTER_ENCRYPTION_KEY_V{n}`, ni de ninguna otra forma.

```python
# Master keys anteriores, solo para descifrar. Ejemplo:
# {"v1": b"<master key anterior>"}
_LEGACY_MASTER_KEYS: dict[str, bytes] = {}
```

En otras palabras: **el versionamiento está diseñado en el servicio pero no implementado como flujo operativo.** `EnvKeyProvider` únicamente resuelve la llave *actual*; no resuelve llaves legacy. Si en algún momento se necesita usar versionamiento, queda a criterio de quien lo implemente decidir *cómo* se provisionan esas llaves anteriores (variable de entorno adicional, secretos manager, etc.) y cablear esa lectura en el código — hoy no existe.

**Recomendación:** dado que no está implementado, si surge la necesidad de conservar datos cifrados con una master key anterior, la opción más simple es crear una variable de entorno nueva por versión (p. ej. `MASTER_ENCRYPTION_KEY_V1`) y cargarla explícitamente en `_LEGACY_MASTER_KEYS` en el código en ese momento — no asumir que ya funciona. Dicho esto, la preferencia general de este documento (§2, §9) sigue siendo **revocar y regenerar por completo** en vez de versionar, precisamente porque versionar implica mantener una llave potencialmente comprometida viva más tiempo. Versionar solo tiene sentido cuando hay datos genuinamente no regenerables que deban conservarse — no como atajo para evitar volver a registrar credenciales con los proveedores.

**Qué pasa si falta la llave de una versión referenciada — confirmado en código:** `_master_key_for_version()` lanza explícitamente `DecryptionError` con el mensaje `"No se conoce ninguna master key para la versión '{version}'"` cuando la versión no es la actual (`_KEY_VERSION`) ni está en `_LEGACY_MASTER_KEYS`. No falla en silencio: se registra con `logger.exception` y se propaga la excepción. Lo mismo ocurre si el valor cifrado no tiene el prefijo `versión:` esperado (falta el separador `:`) — se lanza `DecryptionError("Formato de valor cifrado inválido")`. Ambos casos son detectables y logueables durante una migración o incidente.

**Cuándo usar versionamiento:** solo cuando existen datos cifrados que deben conservarse y no pueden regenerarse. No es necesario para tokens de sesión (se regeneran) ni, en general, para nada que pueda invalidarse y volver a crear sin costo.

**Cuándo NO usarlo:** conservar una llave comprometida como "legacy" únicamente para no perder datos que en realidad sí podrían regenerarse. Eso mantiene material comprometido operativo más tiempo del necesario.

Las llaves históricas deben eliminarse en cuanto dejen de ser necesarias para descifrar datos que se estén conservando activamente.

---

## 9. Procedimiento detallado ante compromiso

Principio general: **revocar → generar nuevas llaves → invalidar lo antiguo → regenerar → re-registrar credenciales externas → verificar.**

```text
COMPROMISO
    │
    ▼
¿Qué se comprometió?
    │
    ├── SECRET_KEY ────────────► nueva llave → reiniciar → sesiones inválidas → usuarios re-autentican
    │
    ├── Token de sesión ───────► invalidar → regenerar con credencial vigente
    │
    ├── MASTER_ENCRYPTION_KEY ─► nueva llave → clasificar cada valor cifrado:
    │                              ├── regenerable ──► invalidar y regenerar
    │                              └── no regenerable ► versionar (§8) y migrar con cuidado
    │
    └── Credencial de API ─────► revocar en el proveedor → generar nueva → registrar en
                                  CostFlow → cifrar con la master key vigente → invalidar y
                                  regenerar los tokens que dependían de ella
```

**Compromiso simultáneo (SECRET_KEY + MASTER_ENCRYPTION_KEY + base de datos):** trátalo como el peor caso — todas las credenciales de API almacenadas deben considerarse potencialmente expuestas, aunque los registros aparezcan correctamente cifrados. Aplica el flujo anterior para cada tipo de secreto en paralelo, y no des por cerrado el incidente hasta confirmar que ningún componente sigue usando llaves, tokens o credenciales anteriores.

Pasos finales, independientemente de qué se haya comprometido:

1. Verificar que ningún servicio siga usando el material anterior.
2. Investigar el origen de la exposición.

---

## 10. Reglas principales

1. Nunca almacenar llaves reales en Git ni en logs.
2. Nunca reutilizar llaves entre ambientes (desarrollo/producción).
3. Generar llaves solo con un generador criptográficamente seguro.
4. Toda llave expuesta se considera comprometida — sin excepciones ni "probablemente no se vio".
5. Ante compromiso: revocar, sustituir, regenerar — no basta con rotar la llave interna.
6. Regenerar (no conservar) lo que pueda regenerarse: tokens de sesión, en particular.
7. Las credenciales de API se revocan **en el proveedor**, no solo dentro de CostFlow.
8. Usar versionamiento de `MASTER_ENCRYPTION_KEY` solo cuando haya datos no regenerables que deban conservarse — es la excepción, no el procedimiento por defecto.
9. Eliminar llaves históricas en cuanto dejen de ser necesarias.
10. Si la base de datos y una llave de cifrado se comprometen juntas, asumir que todo lo cifrado con esa llave pudo haber sido leído.

El objetivo de cualquier recuperación no es solo tener una llave nueva, sino terminar con un sistema donde ninguna llave, token o credencial comprometidos siga siendo válido o necesario.