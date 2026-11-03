import atexit
from app import DEFAULT_CONTEXT_SECTIONS, app, get_context_service, get_startup_service


from startup_runner import StartupRunner


def initialize():
    get_startup_service().start_application()
    get_context_service().snapshot(sections=DEFAULT_CONTEXT_SECTIONS)


startup_runner = StartupRunner(initialize)
startup_runner.thread.start()

from app import shutdown_backend
atexit.register(shutdown_backend)
atexit.register(startup_runner.stop)
