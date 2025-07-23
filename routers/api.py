from fastapi import APIRouter
from backend.db import get_connection

router = APIRouter()

@router.get("/signals")
def get_signals():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM signals ORDER BY timestamp DESC LIMIT 10")
        rows = cur.fetchall()
        return [dict(row) for row in rows]
