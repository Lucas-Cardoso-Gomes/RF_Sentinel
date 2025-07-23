from fastapi import APIRouter
from utils.rfscanner import toggle_scanner

router = APIRouter()

@router.get("/toggle")
def toggle():
    active = toggle_scanner()
    return {"active": active}
