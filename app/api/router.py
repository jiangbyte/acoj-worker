from app.platform.module import build_api_router, load_module_specs

router = build_api_router(load_module_specs())
