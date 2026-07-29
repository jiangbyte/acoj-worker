"""Load Celery tasks declared by modules."""

from app.platform.module import load_declared_tasks, load_module_specs

load_declared_tasks(load_module_specs())
