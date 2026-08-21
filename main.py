import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config, db
from app.routes import admin, auth, catalog, chat, customers, system

log = logging.getLogger("sai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.validate_security_config()
    db.init_db()
    db.seed_admin()
    log.info("[SAI] v%s siap (db=sqlite, auth=%s)", config.APP_VERSION, config.AUTH_ENABLED)
    yield


app = FastAPI(title="Sales AI Assistant API", version=config.APP_VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware,
                   allow_origins=config.cors_origins,
                   allow_methods=["*"],
                   allow_headers=["*"])

app.include_router(system.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(chat.router)
app.include_router(customers.router)
app.include_router(catalog.router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
