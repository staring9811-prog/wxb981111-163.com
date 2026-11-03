"""工作台（PAGE-F15-02，DEC-101）。骨架版：后续由工作台模块补齐各区块。"""
from fastapi import APIRouter, Request

from ..auth import any_user
from .ui import render

router = APIRouter()


@router.get("/")
def home(request: Request, user=any_user):
    return render(request, "home.html", "PAGE-F15-02", "工作台")
