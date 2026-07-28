import multiprocessing
import os

# -----------------------------------------------------------------------------
# Servidor
# -----------------------------------------------------------------------------

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")
backlog = int(os.getenv("GUNICORN_BACKLOG", "2048"))

# -----------------------------------------------------------------------------
# Workers
# -----------------------------------------------------------------------------

workers = int(
    os.getenv(
        "GUNICORN_WORKERS",
        multiprocessing.cpu_count() * 2 + 1,
    )
)

threads = int(os.getenv("GUNICORN_THREADS", "2"))

worker_class = "gthread"

# -----------------------------------------------------------------------------
# Timeouts
# -----------------------------------------------------------------------------

# Tus consultas a proveedores pueden tardar más que una aplicación normal
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))

graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))

keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))

# -----------------------------------------------------------------------------
# Reinicio preventivo de workers
# -----------------------------------------------------------------------------

max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "1000"))

max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "100"))

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

accesslog = "-"
errorlog = "-"

loglevel = os.getenv("LOG_LEVEL", "info").lower()

capture_output = True

# -----------------------------------------------------------------------------
# Proceso
# -----------------------------------------------------------------------------

daemon = False

preload_app = False

reuse_port = False

# -----------------------------------------------------------------------------
# Información del proceso
# -----------------------------------------------------------------------------

proc_name = "costflow"

# -----------------------------------------------------------------------------
# Temporales
# -----------------------------------------------------------------------------

worker_tmp_dir = "/dev/shm"

# -----------------------------------------------------------------------------
# HTTP
# -----------------------------------------------------------------------------

limit_request_line = 4094

limit_request_fields = 100

limit_request_field_size = 8190
