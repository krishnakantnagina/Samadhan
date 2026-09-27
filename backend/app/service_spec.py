"""S03 — Service spec loader (T11). Spec: docs/specs/S03-service-spec-format.md.

Turns `specs/<service>.yaml` into typed models and fails fast at startup: unknown keys, duplicate
keys, duplicate fields, a required field without a question, or a `service` that does not match
the filename all raise `SpecError` naming the file, the key path and the reason.

Either of us can change this file. If you do, update docs/specs/S03-service-spec-format.md and
tell the other.
"""

from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.schemas import ComplaintStatus, OfficeLevel

SNAKE_CASE = r"^[a-z][a-z0-9_]*$"


class SpecError(ValueError):
    """A service spec file is missing, unreadable, or breaks S03."""


class SpecModel(BaseModel):
    """Base for all spec models. Unknown keys are rejected (S03, loader rules)."""

    model_config = ConfigDict(extra="forbid")


class LocalizedText(SpecModel):
    hi: str = Field(min_length=1)
    en: str = Field(min_length=1)


class EnumValue(LocalizedText):
    value: str = Field(pattern=SNAKE_CASE)


class Pilot(SpecModel):
    city: str = Field(min_length=1)
    wards: int = Field(gt=0)


class OutOfScope(SpecModel):
    examples: list[str] = Field(min_length=1)
    reply: LocalizedText


class Routing(SpecModel):
    """S03 routing block. Levels and statuses are the S01/S02 enums, not new lists."""

    min_confidence: float = Field(ge=0, le=1)
    fallback_level: OfficeLevel
    fallback_status: ComplaintStatus
    max_match_distance_km: float = Field(gt=0)


# --- Fields ------------------------------------------------------------------------------


class FieldBase(SpecModel):
    name: str = Field(pattern=SNAKE_CASE)
    required: bool
    label: LocalizedText
    question: LocalizedText | None = None
    hint: str | None = None
    rule: str | None = None  # free-text note for humans; ignored by code

    @model_validator(mode="after")
    def _required_needs_question(self) -> "FieldBase":
        if self.required and self.question is None:
            raise ValueError(f"field '{self.name}' is required, so it needs a question (hi and en)")
        return self


class EnumField(FieldBase):
    type: Literal["enum"]
    values: list[EnumValue] = Field(min_length=2)

    @model_validator(mode="after")
    def _values_unique(self) -> "EnumField":
        ids = [v.value for v in self.values]
        if len(set(ids)) != len(ids):
            raise ValueError(f"field '{self.name}': enum values must be unique")
        return self


class IntegerField(FieldBase):
    type: Literal["integer"]
    min: int
    max: int

    @model_validator(mode="after")
    def _min_le_max(self) -> "IntegerField":
        if self.min > self.max:
            raise ValueError(f"field '{self.name}': min must be <= max")
        return self


class StringField(FieldBase):
    type: Literal["string"]
    max_length: int = Field(gt=0)


class Gps(SpecModel):
    lat: tuple[float, float]
    lng: tuple[float, float]

    @model_validator(mode="after")
    def _ranges(self) -> "Gps":
        for label, (low, high), bound in (("lat", self.lat, 90), ("lng", self.lng, 180)):
            if not -bound <= low <= high <= bound:
                raise ValueError(f"gps.{label} must be a range within -{bound}..{bound}")
        return self


class PlaceName(SpecModel):
    min_length: int = Field(ge=1)
    max_length: int = Field(ge=1)

    @model_validator(mode="after")
    def _min_le_max(self) -> "PlaceName":
        if self.min_length > self.max_length:
            raise ValueError("place_name: min_length must be <= max_length")
        return self


class Accepts(SpecModel):
    gps: Gps
    place_name: PlaceName


class LocationField(FieldBase):
    type: Literal["location"]
    ask_for: str | None = None  # value of `ask_for` in the S01 response; defaults to `name`
    accepts: Accepts

    @model_validator(mode="after")
    def _default_ask_for(self) -> "LocationField":
        if self.ask_for is None:
            self.ask_for = self.name
        return self


FieldSpec = Annotated[
    EnumField | IntegerField | StringField | LocationField, Field(discriminator="type")
]


# --- Service spec ------------------------------------------------------------------------


class ServiceSpec(SpecModel):
    spec_version: Literal[1]
    service: str = Field(pattern=SNAKE_CASE)
    department: str = Field(min_length=1)
    label: LocalizedText
    recognise: list[str] = Field(min_length=1)
    out_of_scope: OutOfScope
    pilot: Pilot
    routing: Routing
    confirmation: Literal["required"]
    fields: list[FieldSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _fields_consistent(self) -> "ServiceSpec":
        names = [f.name for f in self.fields]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"duplicate field name(s): {', '.join(dupes)}")
        if not self.required_fields():
            raise ValueError("at least one field must be required")
        return self

    def required_fields(self) -> list[FieldSpec]:
        return [f for f in self.fields if f.required]

    def field(self, name: str) -> FieldSpec | None:
        return next((f for f in self.fields if f.name == name), None)


# --- Loading -----------------------------------------------------------------------------


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects a mapping key written twice (PyYAML lets the last one win)."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _describe(path: Path, exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        where = ".".join(str(part) for part in err["loc"]) or "(top level)"
        lines.append(f"{path.name}: {where}: {err['msg'].removeprefix('Value error, ')}")
    return "\n".join(lines)


def load_spec(path: str | Path) -> ServiceSpec:
    """Load and validate one spec file. Raises SpecError with file, key path and reason."""
    path = Path(path)
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_StrictLoader)
    except OSError as exc:
        raise SpecError(f"{path}: cannot read file: {exc}") from exc
    except yaml.YAMLError as exc:
        raise SpecError(f"{path.name}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise SpecError(f"{path.name}: the top level must be a mapping of keys")
    try:
        spec = ServiceSpec.model_validate(raw)
    except ValidationError as exc:
        raise SpecError(_describe(path, exc)) from exc
    if spec.service != path.stem:
        raise SpecError(
            f"{path.name}: service '{spec.service}' must equal the filename '{path.stem}'"
        )
    return spec


def load_specs(directory: str | Path) -> dict[str, ServiceSpec]:
    """Load every `*.yaml` in `directory`, keyed by service id. Loaded once at startup."""
    directory = Path(directory)
    specs: dict[str, ServiceSpec] = {}
    for path in sorted(directory.glob("*.yaml")):
        spec = load_spec(path)  # service == filename, so ids are unique within a directory
        specs[spec.service] = spec
    if not specs:
        raise SpecError(f"{directory}: no service specs (*.yaml) found")
    return specs
