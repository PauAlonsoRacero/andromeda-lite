"""commands.py — Slash commands disponibles para el chat."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.slash_commands import list_commands

router = APIRouter()


@router.get("")
async def commands() -> JSONResponse:
    return JSONResponse(content={"commands": list_commands()})
