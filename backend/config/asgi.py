"""ASGI entry point, used by the `stream` service (uvicorn) for Server-Sent Events. The rest of
the API stays on WSGI (`backend`): under ASGI, sync views would share one thread."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_asgi_application()
