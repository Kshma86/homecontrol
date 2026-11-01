import atexit
from app import DEFAULT_CONTEXT_SECTIONS, app, get_context_service, get_startup_service


get_startup_service().start_application()
get_context_service().snapshot(sections=DEFAULT_CONTEXT_SECTIONS)

from app import shutdown_backend
atexit.register(shutdown_backend)
