from __future__ import annotations
from typing import Any
from plaik_sdk import PublicHandlerRef
from plaik_contracts import PublicDeclarationKind, PublicResponseEnvelope

def bind(runtime: Any, kind: str, ident: str, fn: Any) -> None:
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind(kind), id=ident), fn)

def response(value: Any) -> PublicResponseEnvelope:
    return PublicResponseEnvelope(data=value if value is not None else {})
