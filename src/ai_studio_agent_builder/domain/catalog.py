from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal


class TemplateId(StrEnum):
    ONE_PROMPT = "one_prompt"
    RAG = "rag"


class ComponentKind(StrEnum):
    TEMPLATE = "template"
    PROMPT = "prompt"
    KNOWLEDGE_BASE = "knowledge_base"
    APPLICATION_TOOL = "application_tool"
    INTERNAL_TOOL = "internal_tool"


@dataclass(frozen=True)
class ComponentDescriptor:
    component_id: str
    kind: ComponentKind
    title: str
    description: str
    public: bool = True
    parameters: dict[str, Any] | None = None

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "component_id": self.component_id,
            "kind": self.kind.value,
            "title": self.title,
            "description": self.description,
            "public": self.public,
        }
        if self.parameters:
            record["parameters"] = dict(self.parameters)
        return record


@dataclass(frozen=True)
class TemplateDescriptor:
    template_id: TemplateId
    title: str
    description: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    components: tuple[str, ...]

    def to_record(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id.value,
            "title": self.title,
            "description": self.description,
            "required_fields": list(self.required_fields),
            "optional_fields": list(self.optional_fields),
            "components": list(self.components),
        }


BASE_REQUIRED_FIELDS = (
    "purpose",
    "instructions",
    "expected_result",
)

TEMPLATES: dict[TemplateId, TemplateDescriptor] = {
    TemplateId.ONE_PROMPT: TemplateDescriptor(
        template_id=TemplateId.ONE_PROMPT,
        title="One-prompt agent",
        description=(
            "Simple LLM application described by a reusable system prompt without "
            "an external knowledge base."
        ),
        required_fields=BASE_REQUIRED_FIELDS,
        optional_fields=("audience", "inputs", "constraints", "parameters", "tools"),
        components=("system_prompt", "web_search"),
    ),
    TemplateId.RAG: TemplateDescriptor(
        template_id=TemplateId.RAG,
        title="RAG agent",
        description=(
            "LLM application that combines a system prompt with a vector knowledge "
            "base and a knowledge-search tool."
        ),
        required_fields=(
            *BASE_REQUIRED_FIELDS,
            "knowledge_sources",
            "tools",
            "parameters.index_id",
        ),
        optional_fields=("audience", "inputs", "constraints", "parameters.ttl_days"),
        components=("system_prompt", "vector_index", "knowledge_search"),
    ),
}

COMPONENTS: dict[str, ComponentDescriptor] = {
    "system_prompt": ComponentDescriptor(
        component_id="system_prompt",
        kind=ComponentKind.PROMPT,
        title="System prompt",
        description="Instruction block that defines the created agent behavior.",
    ),
    "vector_index": ComponentDescriptor(
        component_id="vector_index",
        kind=ComponentKind.KNOWLEDGE_BASE,
        title="Vector index",
        description="AI Studio vector store created from user-provided files.",
        parameters={"ttl_days": 1},
    ),
    "knowledge_search": ComponentDescriptor(
        component_id="knowledge_search",
        kind=ComponentKind.APPLICATION_TOOL,
        title="Knowledge search",
        description=(
            "Application-level search tool available to the created RAG agent. "
            "It uses the created vector index through its index_id."
        ),
        parameters={"requires": "parameters.index_id"},
    ),
    "web_search": ComponentDescriptor(
        component_id="web_search",
        kind=ComponentKind.APPLICATION_TOOL,
        title="Web search",
        description="Searches the public web for current information.",
        parameters={"search_context_size": "medium"},
    ),
    "delegate_rag": ComponentDescriptor(
        component_id="delegate_rag",
        kind=ComponentKind.INTERNAL_TOOL,
        title="Delegate to RAG",
        description="Internal coordinator routing tool; not exported as an agent tool.",
        public=False,
    ),
    "delegate_one_prompt": ComponentDescriptor(
        component_id="delegate_one_prompt",
        kind=ComponentKind.INTERNAL_TOOL,
        title="Delegate to one-prompt",
        description="Internal coordinator routing tool; not exported as an agent tool.",
        public=False,
    ),
    "finish_dialog": ComponentDescriptor(
        component_id="finish_dialog",
        kind=ComponentKind.INTERNAL_TOOL,
        title="Finish dialog",
        description="Internal session-control tool; not exported as an agent tool.",
        public=False,
    ),
}


def template_required_fields(template: TemplateId | str) -> tuple[str, ...]:
    return template_descriptor(template).required_fields


def template_descriptor(template: TemplateId | str) -> TemplateDescriptor:
    template_id = TemplateId(template)
    return TEMPLATES[template_id]


def component_descriptor(component_id: str) -> ComponentDescriptor:
    return COMPONENTS[component_id]


def is_public_application_tool(component_id: str) -> bool:
    component = COMPONENTS.get(component_id)
    return (
        component is not None
        and component.public
        and component.kind is ComponentKind.APPLICATION_TOOL
    )


def catalog_record(
    *, visibility: Literal["public", "all"] = "public"
) -> dict[str, list[dict[str, Any]]]:
    include_private = visibility == "all"
    return {
        "templates": [descriptor.to_record() for descriptor in TEMPLATES.values()],
        "components": [
            component.to_record()
            for component in COMPONENTS.values()
            if include_private or component.public
        ],
    }
