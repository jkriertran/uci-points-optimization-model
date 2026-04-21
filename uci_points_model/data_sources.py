from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from .historical_data_import import (
    DEFAULT_IMPORTED_ROOT,
    get_historical_import_spec,
    imported_dataset_path,
    load_imported_historical_dataset,
    validate_historical_import,
)
from .source_registry import (
    SOURCE_DIRECT_SCRAPE,
    SOURCE_FIRECRAWL,
    SOURCE_IMPORTED_HISTORY,
    SOURCE_LOCAL_ARTIFACT,
    SOURCE_MANUAL,
    get_source_policy,
)


@dataclass(frozen=True)
class DatasetSourceDecision:
    dataset_key: str
    selected_source: str
    reason: str
    path: str = ""


def select_dataset_source(
    dataset_key: str,
    import_root: str | Path = DEFAULT_IMPORTED_ROOT,
    local_artifact_paths: Iterable[str | Path] | None = None,
) -> DatasetSourceDecision:
    policy = get_source_policy(dataset_key)
    validation_report = validate_historical_import(
        import_root=import_root,
        specs=(get_historical_import_spec(policy.import_key),) if policy.import_key else None,
    )

    for source_name in policy.fallback_order:
        if source_name == SOURCE_IMPORTED_HISTORY and policy.import_key:
            import_result = validation_report.file_results.get(policy.import_key)
            imported_path = imported_dataset_path(key=policy.import_key, import_root=import_root)
            if import_result and import_result.passed:
                return DatasetSourceDecision(
                    dataset_key=dataset_key,
                    selected_source=SOURCE_IMPORTED_HISTORY,
                    reason="Validated imported upstream historical dataset is available.",
                    path=str(imported_path),
                )

        if source_name == SOURCE_LOCAL_ARTIFACT:
            for candidate in local_artifact_paths or ():
                path = Path(candidate)
                if path.exists():
                    return DatasetSourceDecision(
                        dataset_key=dataset_key,
                        selected_source=SOURCE_LOCAL_ARTIFACT,
                        reason="Local production artifact is available.",
                        path=str(path),
                    )

        if source_name == SOURCE_DIRECT_SCRAPE:
            return DatasetSourceDecision(
                dataset_key=dataset_key,
                selected_source=SOURCE_DIRECT_SCRAPE,
                reason="Imported data is unavailable or invalid; direct scrape is the next fallback.",
            )

        if source_name == SOURCE_FIRECRAWL:
            return DatasetSourceDecision(
                dataset_key=dataset_key,
                selected_source=SOURCE_FIRECRAWL,
                reason="Firecrawl is the next fallback after direct scraping.",
            )

        if source_name == SOURCE_MANUAL:
            return DatasetSourceDecision(
                dataset_key=dataset_key,
                selected_source=SOURCE_MANUAL,
                reason="Manual inspection is the last resort.",
            )

    raise RuntimeError(f"No source decision available for dataset key: {dataset_key}")


def load_dataset_from_decision(decision: DatasetSourceDecision) -> pd.DataFrame:
    if decision.selected_source in {SOURCE_IMPORTED_HISTORY, SOURCE_LOCAL_ARTIFACT} and decision.path:
        return pd.read_csv(decision.path, compression="infer")
    return pd.DataFrame()


def load_historical_dataset(
    dataset_key: str,
    import_root: str | Path = DEFAULT_IMPORTED_ROOT,
) -> tuple[pd.DataFrame, DatasetSourceDecision]:
    decision = select_dataset_source(dataset_key=dataset_key, import_root=import_root)
    if decision.selected_source == SOURCE_IMPORTED_HISTORY:
        dataset = load_imported_historical_dataset(key=dataset_key, import_root=import_root)
    else:
        dataset = load_dataset_from_decision(decision)
    dataset.attrs["source_decision"] = {
        "dataset_key": decision.dataset_key,
        "selected_source": decision.selected_source,
        "reason": decision.reason,
        "path": decision.path,
    }
    return dataset, decision
