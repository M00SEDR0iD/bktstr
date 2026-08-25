from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType

from bktstr.variables import (
    DataTier,
    ResearchVariableDefinition,
    VariableContractError,
    VariableRef,
)


_TIER_ORDER = {DataTier.A: 0, DataTier.B: 1, DataTier.C: 2, DataTier.D: 3}
_Identity = tuple[str, str]


class VariableRegistry:
    """Append-only registry of immutable, exact-version variable definitions."""

    def __init__(self) -> None:
        self._definitions: dict[_Identity, ResearchVariableDefinition] = {}

    @property
    def definitions(self) -> Mapping[_Identity, ResearchVariableDefinition]:
        return MappingProxyType(self._definitions)

    def register(self, definition: ResearchVariableDefinition) -> ResearchVariableDefinition:
        if not isinstance(definition, ResearchVariableDefinition):
            raise VariableContractError(
                "registry definitions must be ResearchVariableDefinition values",
                code="invalid_definition",
            )
        identity = (definition.id, definition.version)
        if identity in self._definitions:
            raise VariableContractError(
                f"variable {definition.id!r} version {definition.version!r} is already registered",
                code="duplicate_variable_identity",
                details={"id": definition.id, "version": definition.version},
            )
        self._definitions[identity] = definition
        return definition

    def get(
        self, variable: VariableRef | str, version: str | None = None
    ) -> ResearchVariableDefinition | None:
        identity = self._identity(variable, version)
        return None if identity is None else self._definitions.get(identity)

    def require(
        self, variable: VariableRef | str, version: str | None = None
    ) -> ResearchVariableDefinition:
        identity = self._identity(variable, version)
        if identity is None:
            variable_id = variable.id if isinstance(variable, VariableRef) else variable
            raise self._unknown_variable(variable_id, version)
        definition = self._definitions.get(identity)
        if definition is None:
            raise self._unknown_variable(*identity)
        return definition

    def validate_dependencies(
        self, references: Sequence[VariableRef]
    ) -> tuple[ResearchVariableDefinition, ...]:
        states: dict[_Identity, str] = {}
        stack: list[_Identity] = []
        ordered: list[ResearchVariableDefinition] = []

        def visit(reference: VariableRef) -> None:
            definition = self.require(reference)
            if reference.tier is not definition.tier:
                raise VariableContractError(
                    f"reference tier {reference.tier.value} does not match variable tier {definition.tier.value}",
                    code="illegal_tier_dependency",
                    details={
                        "variable": (definition.id, definition.version),
                        "variable_tier": definition.tier.value,
                        "reference_tier": reference.tier.value,
                    },
                )
            identity = (definition.id, definition.version)
            state = states.get(identity)
            if state == "complete":
                return
            if state == "visiting":
                cycle_start = stack.index(identity)
                raise VariableContractError(
                    "variable dependency cycle detected",
                    code="dependency_cycle",
                    details={"cycle": tuple(stack[cycle_start:] + [identity])},
                )

            states[identity] = "visiting"
            stack.append(identity)
            for dependency in definition.inputs:
                dependency_definition = self.require(dependency)
                self._validate_tier_dependency(definition, dependency, dependency_definition)
                visit(dependency)
            stack.pop()
            states[identity] = "complete"
            ordered.append(definition)

        for reference in references:
            if not isinstance(reference, VariableRef):
                raise VariableContractError(
                    "dependency roots must be VariableRef values",
                    code="invalid_dependency_reference",
                )
            visit(reference)
        return tuple(ordered)

    def _identity(self, variable: VariableRef | str, version: str | None) -> _Identity | None:
        if isinstance(variable, VariableRef):
            if version is not None and version != variable.version:
                raise VariableContractError(
                    "VariableRef version cannot be overridden",
                    code="invalid_variable_reference",
                )
            return (variable.id, variable.version)
        if not isinstance(variable, str):
            raise VariableContractError(
                "variable lookup requires a VariableRef or variable ID",
                code="invalid_variable_reference",
            )
        if version is not None:
            return (variable, version)

        matches = [identity for identity in self._definitions if identity[0] == variable]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            return None
        raise VariableContractError(
            f"variable {variable!r} has multiple registered versions; an exact version is required",
            code="ambiguous_variable_version",
            details={"id": variable, "versions": tuple(identity[1] for identity in matches)},
        )

    @staticmethod
    def _unknown_variable(variable_id: str, version: str | None) -> VariableContractError:
        details = {"id": variable_id}
        if version is not None:
            details["version"] = version
        return VariableContractError(
            f"variable {variable_id!r} version {version!r} is not registered",
            code="unknown_variable",
            details=details,
        )

    @staticmethod
    def _validate_tier_dependency(
        definition: ResearchVariableDefinition,
        dependency: VariableRef,
        dependency_definition: ResearchVariableDefinition,
    ) -> None:
        dependency_tier = dependency_definition.tier
        if dependency.tier is not dependency_tier or _TIER_ORDER[definition.tier] < _TIER_ORDER[dependency_tier]:
            raise VariableContractError(
                f"tier {definition.tier.value} cannot depend on tier {dependency_tier.value}",
                code="illegal_tier_dependency",
                details={
                    "variable": (definition.id, definition.version),
                    "variable_tier": definition.tier.value,
                    "dependency": (dependency_definition.id, dependency_definition.version),
                    "dependency_tier": dependency_tier.value,
                },
            )
