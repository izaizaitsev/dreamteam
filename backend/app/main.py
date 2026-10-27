"""FastAPI composition root."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .repositories import sqlite as storage
from .services.builtin_templates import seed_builtin_templates
from .api import auth, system, settings, imports, appeals, drafts, templates, index, audit
from .core.sessions import init_sessions


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    init_sessions()
    seed_builtin_templates()
    yield


app = FastAPI(title="DreamTeam", lifespan=lifespan)
for module in (auth, system, settings, imports, appeals, drafts, templates, index, audit):
    app.include_router(module.router)
