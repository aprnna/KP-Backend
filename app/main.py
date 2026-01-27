from app.core.server import create_application

# Create configured application
app = create_application()

# Export app for uvicorn
__all__ = ["app"]