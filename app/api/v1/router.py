from fastapi import APIRouter
from app.api.v1.routes import ping_route
from app.api.v1 import scrape, jobs, sinta_authors, sinta_articles

router_v1 = APIRouter()

# Include existing routes
router_v1.include_router(ping_route.router)

# Include new scraping routes
router_v1.include_router(
    scrape.router, 
    prefix="/scrape", 
    tags=["scrape"]
)
router_v1.include_router(
    jobs.router, 
    prefix="/jobs", 
    tags=["jobs"]
)
router_v1.include_router(
    sinta_authors.router,
    prefix="/sinta-authors",
    tags=["sinta_authors"]
)
router_v1.include_router(
    sinta_articles.router,
    prefix="/sinta-articles",
    tags=["sinta_articles"]
)