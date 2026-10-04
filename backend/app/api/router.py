from fastapi import APIRouter
from app.api import exports, lanes, locations, refills, sales
api_router = APIRouter()

@api_router.get("/health")
def health():
    return {"status": "ok"}

api_router.include_router(locations.router)
api_router.include_router(lanes.router)
api_router.include_router(sales.router)
api_router.include_router(refills.router)
api_router.include_router(exports.router)
