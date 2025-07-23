from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from routers import scanner, api, dashboard
import utils.init

app = FastAPI(title="RFSentinel")

app.include_router(scanner.router, prefix="/scanner")
app.include_router(api.router, prefix="/api")
app.include_router(dashboard.router)

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")
