from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class SeriesFinding:
    case_id: str
    phase: str
    phase_source: str
    relative_dir: str
    series_dir: str
    file_count: int
    readable_count: int
    unreadable_count: int
    modality: str | None
    series_description: str | None
    manufacturer: str | None
    manufacturer_model_name: str | None
    convolution_kernel: str | None
    pixel_spacing_unique: list[str]
    slice_thickness_unique: list[str]
    orientation_unique: list[str]
    series_uid_unique_count: int
    sop_uid_unique_count: int
    instance_number_unique_count: int
    image_position_unique_count: int
    required_tag_missing: list[str]
    issues: list[str]
    severity: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class CaseFinding:
    case_id: str
    recognized_phases: list[str]
    missing_phases: list[str]
    unknown_phase_series: list[str]
    duplicate_phase_map: dict[str, list[str]]
    series_issue_summary: list[str]
    issues: list[str]
    severity: str

    def to_dict(self) -> dict:
        return asdict(self)
