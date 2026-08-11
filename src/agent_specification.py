"""Compatibility imports for the packaged AgentSpecification contract.

New code must import :mod:`ai_studio_agent_builder.domain.specification`
directly. This module is removed before the public ``v0.1.0`` release.
"""

from ai_studio_agent_builder.domain.specification import *  # noqa: F403
from ai_studio_agent_builder.domain.specification_codec import (  # noqa: F401
    InvalidSpecificationJSONError,
    InvalidSpecificationRootError,
    dump_agent_specification,
    dumps_agent_specification,
    load_agent_specification,
    loads_agent_specification,
)
