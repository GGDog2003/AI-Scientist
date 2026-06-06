def main(*args, **kwargs):
    from app.main import main as app_main

    return app_main(*args, **kwargs)


__all__ = ["main"]
