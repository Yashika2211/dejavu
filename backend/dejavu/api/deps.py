"""Route dependencies."""

from typing import Annotated

from fastapi import Depends, Request

from dejavu.api.services import Services


def get_services(request: Request) -> Services:
    return request.app.state.services


Svc = Annotated[Services, Depends(get_services)]
