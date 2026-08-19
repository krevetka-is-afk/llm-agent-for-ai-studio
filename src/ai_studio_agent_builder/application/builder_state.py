from collections.abc import Mapping
from dataclasses import replace

from ..domain.catalog import (
    TemplateId,
    is_public_application_tool,
    template_descriptor,
)
from ..domain.routing import ConversationOptions
from ..domain.specification import (
    AgentSpecification,
    KnowledgeSource,
    ToolDescriptor,
    specification_template_for,
)


class ConversationState:
    def __init__(
        self,
        state: ConversationOptions = ConversationOptions.COORDINATOR,
        *,
        draft_agent_specification: AgentSpecification | None = None,
        latest_agent_specification: AgentSpecification | None = None,
        pending_filenames_by_file_id: Mapping[str, str] | None = None,
    ) -> None:
        self.state = state
        self.draft_agent_specification = draft_agent_specification
        self.latest_agent_specification = latest_agent_specification
        self._pending_filenames_by_file_id = dict(pending_filenames_by_file_id or {})

    def copy(self) -> "ConversationState":
        return ConversationState(
            self.state,
            draft_agent_specification=self.draft_agent_specification,
            latest_agent_specification=self.latest_agent_specification,
            pending_filenames_by_file_id=self._pending_filenames_by_file_id,
        )

    def commit_from(self, other: "ConversationState") -> None:
        self.state = other.state
        self.draft_agent_specification = other.draft_agent_specification
        self.latest_agent_specification = other.latest_agent_specification
        self._pending_filenames_by_file_id = dict(other._pending_filenames_by_file_id)

    @property
    def pending_file_ids(self) -> tuple[str, ...]:
        return tuple(self._pending_filenames_by_file_id)

    @property
    def pending_filenames_by_file_id(self) -> dict[str, str]:
        return dict(self._pending_filenames_by_file_id)

    def register_pending_files(self, filenames_by_file_id: Mapping[str, str]) -> None:
        for file_id, filename in filenames_by_file_id.items():
            if file_id and filename:
                self._pending_filenames_by_file_id[file_id] = filename

    @property
    def agent_specification(self) -> AgentSpecification | None:
        return self.draft_agent_specification or self.latest_agent_specification

    def update_state(self, new_state: ConversationOptions) -> None:
        if new_state is not ConversationOptions.RAG:
            self._pending_filenames_by_file_id.clear()
        if new_state is not ConversationOptions.COORDINATOR:
            target_template = specification_template_for(new_state)
            current = self.agent_specification
            if current is not None and current.template is not target_template:
                self.draft_agent_specification = _retarget_compatible_tools(
                    current,
                    target_template,
                )
                self.latest_agent_specification = None
        self.state = new_state

    def reset_state(self) -> None:
        self.state = ConversationOptions.COORDINATOR
        self.draft_agent_specification = None
        self.latest_agent_specification = None
        self._pending_filenames_by_file_id.clear()

    def finish_dialog(self) -> None:
        self.state = ConversationOptions.COORDINATOR
        self._pending_filenames_by_file_id.clear()
        if self.latest_agent_specification is not None:
            self.draft_agent_specification = None

    def current_or_new_specification(self) -> AgentSpecification:
        template = specification_template_for(self.state)
        current = self.draft_agent_specification
        if current is not None and current.template is template:
            return current
        return AgentSpecification(template=template)

    def update_agent_specification(self, specification: AgentSpecification) -> None:
        specification = specification.with_validation_status()
        self.draft_agent_specification = specification
        self.latest_agent_specification = None

    def import_agent_specification(self, specification: AgentSpecification) -> None:
        """Adopt a serialized specification without treating it as a draft."""
        target_state = (
            ConversationOptions.RAG
            if specification.template.value == "rag"
            else ConversationOptions.ONE_PROMPT
        )
        self.update_state(target_state)
        imported = specification.with_validation_status()
        self._pending_filenames_by_file_id.clear()
        if imported.validate().is_ready:
            self.draft_agent_specification = None
            self.latest_agent_specification = imported
        else:
            self.draft_agent_specification = imported
            self.latest_agent_specification = None

    def finalize_agent_specification(self) -> AgentSpecification:
        specification = self.current_or_new_specification().with_validation_status()
        if specification.validate().is_ready:
            specification = replace(
                specification, status=specification.validate().status
            )
            self.latest_agent_specification = specification
        self.draft_agent_specification = specification
        return specification

    def attach_vector_index(
        self,
        *,
        index_id: str,
        index_name: str,
        file_ids: tuple[str, ...],
        source_titles: Mapping[str, str] | None = None,
        ttl_days: int = 1,
    ) -> AgentSpecification:
        consumed_file_ids = set(file_ids)
        self._pending_filenames_by_file_id = {
            file_id: filename
            for file_id, filename in self._pending_filenames_by_file_id.items()
            if file_id not in consumed_file_ids
        }
        specification = self.current_or_new_specification()
        sources_by_id = {
            source.source_id: source for source in specification.knowledge_sources
        }
        for file_id in file_ids:
            sources_by_id[file_id] = KnowledgeSource(
                source_id=file_id,
                title=(source_titles or {}).get(file_id, file_id),
                kind="uploaded_file",
                reference=file_id,
            )
        tools_by_id = {tool.tool_id: tool for tool in specification.tools}
        tools_by_id["knowledge_search"] = ToolDescriptor(
            tool_id="knowledge_search",
            title="Knowledge search",
            description="Searches the connected AI Studio vector index.",
            parameters={"index_id": index_id, "index_name": index_name},
        )
        parameters = dict(specification.parameters)
        parameters.update(
            {
                "index_id": index_id,
                "index_name": index_name,
                "ttl_days": ttl_days,
            }
        )
        updated = replace(
            specification,
            knowledge_sources=tuple(sources_by_id.values()),
            tools=tuple(tools_by_id.values()),
            parameters=parameters,
        ).with_validation_status()
        self.update_agent_specification(updated)
        return updated


def _retarget_compatible_tools(
    specification: AgentSpecification,
    target_template: TemplateId,
) -> AgentSpecification | None:
    allowed_components = set(template_descriptor(target_template).components)
    compatible_tools = tuple(
        tool
        for tool in specification.tools
        if tool.tool_id in allowed_components
        and is_public_application_tool(tool.tool_id)
    )
    if not compatible_tools:
        return None
    return AgentSpecification(
        template=target_template,
        tools=compatible_tools,
    ).with_validation_status()


__all__ = ["ConversationOptions", "ConversationState"]
