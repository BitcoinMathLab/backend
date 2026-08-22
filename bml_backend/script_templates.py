"""Product boundary for constructing standard Bitcoin locking scripts."""
from __future__ import annotations

from src.script import build_standard_script

from bml_backend.models import StandardScriptTemplateRequest, StandardScriptTemplateResponse


class ScriptTemplateError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "invalid-script-template"
        self.message = message


def create_standard_script_template(
    request: StandardScriptTemplateRequest,
) -> StandardScriptTemplateResponse:
    try:
        result = build_standard_script(request.template, bytes.fromhex(request.program_hex))
    except (TypeError, ValueError) as exc:
        raise ScriptTemplateError(str(exc)) from exc

    return StandardScriptTemplateResponse(
        template=result.template.value,
        script_type=result.script_type.value,
        program_hex=request.program_hex,
        script_pubkey_hex=result.script_pubkey.hex(),
        address=result.address,
    )
