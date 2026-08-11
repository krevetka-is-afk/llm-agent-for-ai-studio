from dataclasses import replace
from typing import Any

from agents import RunContextWrapper, function_tool

from ai_studio_agent_builder.builder.context import RequestContext
from ai_studio_agent_builder.domain.specification import (
    build_code_interpreter_tool_descriptor,
    build_web_search_tool_descriptor,
)
from ai_studio_agent_builder.domain.specification_codec import (
    dumps_agent_specification,
)


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_text_tuple(values: list[str] | None) -> tuple[str, ...] | None:
    if values is None:
        return None
    return tuple(value.strip() for value in values if value.strip())


def _specification_response(specification: Any) -> str:
    return dumps_agent_specification(specification, indent=None)


def _update_agent_specification_impl(
    state: Any,
    *,
    purpose: str | None = None,
    audience: str | None = None,
    inputs: list[str] | None = None,
    instructions: str | None = None,
    constraints: list[str] | None = None,
    expected_result: str | None = None,
    web_search: bool | None = None,
    code_interpreter: bool | None = None,
) -> str:
    specification = state.current_or_new_specification()
    updates: dict[str, Any] = {}

    for field_name, value in {
        "purpose": _clean_text(purpose),
        "audience": _clean_text(audience),
        "instructions": _clean_text(instructions),
        "expected_result": _clean_text(expected_result),
    }.items():
        if value is not None:
            updates[field_name] = value

    cleaned_inputs = _clean_text_tuple(inputs)
    if cleaned_inputs is not None:
        updates["inputs"] = cleaned_inputs

    cleaned_constraints = _clean_text_tuple(constraints)
    if cleaned_constraints is not None:
        updates["constraints"] = cleaned_constraints

    if web_search is not None or code_interpreter is not None:
        tools_by_id = {tool.tool_id: tool for tool in specification.tools}
        if web_search is not None:
            if web_search:
                tools_by_id["web_search"] = build_web_search_tool_descriptor()
            else:
                tools_by_id.pop("web_search", None)
        if code_interpreter is not None:
            if code_interpreter:
                tools_by_id["code_interpreter"] = (
                    build_code_interpreter_tool_descriptor()
                )
            else:
                tools_by_id.pop("code_interpreter", None)
        updates["tools"] = tuple(tools_by_id.values())

    updated = replace(specification, **updates).with_validation_status()
    state.update_agent_specification(updated)
    return _specification_response(updated)


def _finalize_agent_specification_impl(state: Any) -> str:
    return _specification_response(state.finalize_agent_specification())


@function_tool
def update_agent_specification(
    ctx: RunContextWrapper[RequestContext],
    purpose: str | None = None,
    audience: str | None = None,
    inputs: list[str] | None = None,
    instructions: str | None = None,
    constraints: list[str] | None = None,
    expected_result: str | None = None,
    web_search: bool | None = None,
    code_interpreter: bool | None = None,
) -> str:
    """
    Deterministically update the draft AgentSpecification from confirmed user
    requirements. The response contains validation status and missing fields.
    """
    return _update_agent_specification_impl(
        ctx.context.state,
        purpose=purpose,
        audience=audience,
        inputs=inputs,
        instructions=instructions,
        constraints=constraints,
        expected_result=expected_result,
        web_search=web_search,
        code_interpreter=code_interpreter,
    )


@function_tool
def finalize_agent_specification(ctx: RunContextWrapper[RequestContext]) -> str:
    """
    Validate the current draft AgentSpecification before finishing the dialog.
    The response remains non-ready when required fields are missing.
    """
    return _finalize_agent_specification_impl(ctx.context.state)
