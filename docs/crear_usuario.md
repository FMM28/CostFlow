# Creación de un usuario administrador

## 1. Propósito

CostFlow proporciona el comando `crear-admin` para crear el usuario administrador inicial del sistema.

El usuario se crea mediante `UserService` con el rol `admin`.

## 2. Requisitos

Antes de ejecutar el comando:

* La aplicación debe estar correctamente configurada.
* La base de datos debe estar disponible.
* Las migraciones deben haberse ejecutado.
* El servicio de la aplicación debe estar disponible.

### Ejecución con Docker

Si CostFlow está desplegado mediante Docker Compose, el comando debe ejecutarse dentro del contenedor de la aplicación.

Desde el directorio del proyecto:

```bash
docker compose exec app flask crear-admin
```

El servicio `app` debe estar en ejecución. Se puede comprobar con:

```bash
docker compose ps
```

Si es necesario iniciar los servicios:

```bash
docker compose up -d
```

Si CostFlow se ejecuta directamente fuera de Docker, el comando es:

```bash
flask crear-admin
```

## 3. Datos solicitados

Durante la ejecución se solicitan los siguientes datos:

| Campo                      | Obligatorio |
| -------------------------- | ----------- |
| Nombre de usuario          | Sí          |
| Email                      | Sí          |
| Nombre                     | Sí          |
| Apellido paterno           | Sí          |
| Apellido materno           | No          |
| Contraseña                 | Sí          |
| Confirmación de contraseña | Sí          |

La contraseña se introduce de forma oculta y debe coincidir con su confirmación.

Si no se proporciona el apellido materno, se almacena como `NULL`.

## 4. Valores asignados automáticamente

El comando establece los siguientes valores:

| Campo        | Valor   |
| ------------ | ------- |
| Rol          | `admin` |
| Número       | `NULL`  |
| Puesto       | `NULL`  |
| URL de firma | `NULL`  |

Estos campos no son solicitados durante el proceso.

## 5. Proceso

El flujo de creación es:

```text
flask crear-admin
        │
        ▼
 Solicitar datos
        │
        ▼
 Solicitar contraseña
        │
        ▼
 Confirmar contraseña
        │
        ▼
 UserService.create()
        │
    ┌───┴───┐
    ▼       ▼
  Error   Éxito
    │       │
    ▼       ▼
Mostrar   Crear
 error    usuario
```

## 6. Resultado

Si la creación es exitosa, se muestra un mensaje similar a:

```text
Administrador creado correctamente (id=1, username='administrador').
```

El `id` corresponde al identificador asignado al usuario por la base de datos.

Si ocurre un error, el comando muestra el mensaje correspondiente y no completa la creación.

## 7. Consideraciones de seguridad

La contraseña debe introducirse únicamente cuando sea solicitada por el comando. No debe incluirse directamente en comandos, scripts o archivos de configuración.

El usuario administrador y sus credenciales deben mantenerse bajo control del personal autorizado.

## 8. Ejemplo

Con Docker Compose:

```bash
docker compose exec app flask crear-admin
```

Resultado esperado:

```text
=== Creación del administrador inicial ===

Nombre de usuario: administrador
Email: administrador@ejemplo.com
Nombre: Francisco
Apellido paterno: Marquez
Apellido materno: Maya
Contraseña:
Confirmar contraseña:

Administrador creado correctamente (id=1, username='administrador').
```
