from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from fnmatch import fnmatch
from typing import Any

from mcp.server.fastmcp import FastMCP

LOGGER = logging.getLogger("metacat_mcp")

READ_ONLY_INSTRUCTIONS = """
Read-only metacat MCP server for Mu2e data discovery.

JARGON INTERPRETATION GUIDE:
- 'art files' or 'art datasets' → use name_pattern='*.art'
- 'raw data' or 'raw files' → use name_pattern='raw.*'
- 'simulation' or 'sim data' → use name_pattern='sim.*'
- 'digitized' or 'dig data' → use name_pattern='dig.*'
- 'reconstructed' or 'reco data' → use name_pattern='rec.*' or 'mcs.*'
- 'ntuples' → use name_pattern='ntd.*.root' for data, 'nts.*.root' for simulation
- 'log files' → use name_pattern='*.log'
- 'production datasets' → use namespace='mu2e' (collaboration-owned)
- 'my datasets' or 'user datasets' → use namespace='<username>' or '<username>_*'
- 'recent datasets' → use created_after_iso_utc with appropriate date

FILE NAMING CONVENTION:
Mu2e files follow: data_tier.owner.description.configuration.sequencer.file_format
- data_tier: sim, dig, mcs, raw, rec, nts, ntd, etc.
- owner: 'mu2e' for production, username for personal
- file_format: .art, .root, .fcl, .log, etc.

NAMESPACE GUIDANCE:
- Collaboration datasets: namespace='mu2e' (always 'mu2e', never 'mu2')
- User datasets: namespace='<username>' or '<username>_*'

Use discover_datasets with appropriate filters. Do not perform write operations.
"""


def _configure_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("METACAT_MCP_LOG_LEVEL", "INFO"),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _client():
    try:
        from metacat.webapi import MetaCatClient
    except Exception as exc:
        raise RuntimeError(
            "Could not import metacat.webapi.MetaCatClient. "
            "Run: mu2einit && muse setup ops"
        ) from exc

    return MetaCatClient()


def _utc_iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _matches_name(name: str, pattern: str | None) -> bool:
    if not pattern:
        return True
    return fnmatch(name, pattern)


def _to_epoch_from_iso(value: str | None) -> float | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _metadata_int(file_obj: dict[str, Any], key: str) -> int | None:
    metadata = file_obj.get("metadata")
    if not isinstance(metadata, dict):
        return None
    return _as_int(metadata.get(key))


def _dataset_record(ds: dict[str, Any]) -> dict[str, Any]:
    namespace = ds.get("namespace")
    name = ds.get("name")
    did = f"{namespace}:{name}" if namespace and name else None
    return {
        "did": did,
        "namespace": namespace,
        "name": name,
        "file_count": ds.get("file_count"),
        "created_timestamp": ds.get("created_timestamp"),
        "created_iso_utc": _utc_iso(ds.get("created_timestamp")),
        "metadata": ds.get("metadata", {}),
        "frozen": ds.get("frozen"),
        "monotonic": ds.get("monotonic"),
        "description": ds.get("description"),
    }


def _file_record(f: dict[str, Any]) -> dict[str, Any]:
    namespace = f.get("namespace")
    name = f.get("name")
    did = f"{namespace}:{name}" if namespace and name else None
    return {
        "did": did,
        "namespace": namespace,
        "name": name,
        "size": f.get("size"),
        "fid": f.get("fid"),
        "created_timestamp": f.get("created_timestamp"),
        "created_iso_utc": _utc_iso(f.get("created_timestamp")),
        "checksums": f.get("checksums", {}),
        "metadata": f.get("metadata", {}),
    }


def create_mcp_server() -> FastMCP:
    mcp = FastMCP("metacat-readonly", instructions=READ_ONLY_INSTRUCTIONS)

    @mcp.tool(
        description=(
            "Discover datasets with explicit filters. Read-only. "
            "Use filters instead of raw query syntax."
        )
    )
    def discover_datasets(
        namespace: str = "mu2e",
        name_pattern: str | None = None,
        created_after_iso_utc: str | None = None,
        created_before_iso_utc: str | None = None,
        non_empty: bool | None = None,
        min_file_count: int | None = None,
        max_file_count: int | None = None,
        oldest_first: bool = False,
        limit: int = 100,
        offset: int = 0,
        include_metadata: bool = False,
    ) -> dict[str, Any]:
        client = _client()

        limit = max(1, min(limit, 1000))
        offset = max(0, offset)

        created_after = _to_epoch_from_iso(created_after_iso_utc)
        created_before = _to_epoch_from_iso(created_before_iso_utc)

        scanned = 0
        rows: list[dict[str, Any]] = []
        warnings: list[str] = []

        # Use wildcard pattern for namespace matching
        namespace_pattern = f"{namespace}*" if namespace and not namespace.endswith("*") else namespace
        
        datasets = client.list_datasets(
            namespace_pattern=namespace_pattern,
            with_counts=False,
        )

        for ds in datasets:
            scanned += 1
            name = ds.get("name")
            if not isinstance(name, str):
                continue
            if not _matches_name(name, name_pattern):
                continue

            created = ds.get("created_timestamp")
            if created_after is not None and (created is None or created < created_after):
                continue
            if created_before is not None and (created is None or created > created_before):
                continue

            row = _dataset_record(ds)

            # Count-based filters require count fetch if not already available.
            need_count = (
                non_empty is not None
                or min_file_count is not None
                or max_file_count is not None
            )
            if need_count and row["did"]:
                details = client.get_dataset(did=row["did"], exact_file_count=False)
                row["file_count"] = details.get("file_count", 0)

            count = row.get("file_count")
            if non_empty is True and (count is None or count <= 0):
                continue
            if non_empty is False and (count is None or count != 0):
                continue
            if min_file_count is not None and (count is None or count < min_file_count):
                continue
            if max_file_count is not None and (count is None or count > max_file_count):
                continue

            if not include_metadata:
                row.pop("metadata", None)

            rows.append(row)

        rows.sort(
            key=lambda item: (item.get("created_timestamp") is None, item.get("created_timestamp")),
            reverse=not oldest_first,
        )

        total = len(rows)
        paged = rows[offset : offset + limit]

        if (min_file_count is not None or max_file_count is not None or non_empty is not None) and scanned > 1000:
            warnings.append(
                "Count-based filtering on broad scope may be slow; narrow namespace/name/time first."
            )

        return {
            "applied_filters": {
                "namespace": namespace,
                "name_pattern": name_pattern,
                "created_after_iso_utc": created_after_iso_utc,
                "created_before_iso_utc": created_before_iso_utc,
                "non_empty": non_empty,
                "min_file_count": min_file_count,
                "max_file_count": max_file_count,
                "oldest_first": oldest_first,
                "limit": limit,
                "offset": offset,
                "include_metadata": include_metadata,
            },
            "total_matches": total,
            "returned": len(paged),
            "results": paged,
            "warnings": warnings,
        }

    @mcp.tool(
        description=(
            "Get dataset details by DID, optionally with an example file and metadata keys. "
            "Read-only."
        )
    )
    def get_dataset_details(
        dataset_did: str,
        include_sample_file: bool = True,
        include_sample_metadata: bool = True,
    ) -> dict[str, Any]:
        client = _client()

        dataset = client.get_dataset(did=dataset_did, exact_file_count=False)
        out: dict[str, Any] = {
            "dataset": _dataset_record(dataset),
            "sample_file": None,
            "sample_metadata_keys": [],
        }

        if include_sample_file:
            files = list(client.query(f"files from {dataset_did} limit 1", with_metadata=False))
            if files:
                sample = _file_record(files[0])
                if include_sample_metadata and sample.get("did"):
                    obj = client.get_file(
                        did=sample["did"], with_metadata=True, with_provenance=False
                    )
                    if obj is not None:
                        sample["metadata"] = obj.get("metadata", {})
                        out["sample_metadata_keys"] = sorted(sample["metadata"].keys())
                out["sample_file"] = sample

        return out

    @mcp.tool(
        description=(
            "Query files from one dataset using common filters (time, size, events, run/subrun) "
            "and sorting. Read-only."
        )
    )
    def query_dataset_files(
        dataset_did: str,
        created_after_iso_utc: str | None = None,
        created_before_iso_utc: str | None = None,
        size_min: int | None = None,
        size_max: int | None = None,
        events_min: int | None = None,
        events_max: int | None = None,
        run_min: int | None = None,
        run_max: int | None = None,
        subrun_min: int | None = None,
        subrun_max: int | None = None,
        sort_by: str = "created_timestamp",
        sort_order: str = "desc",
        limit: int = 100,
        offset: int = 0,
        include_metadata: bool = False,
    ) -> dict[str, Any]:
        allowed_sort = {"created_timestamp", "size", "run", "subrun", "n_events", "name"}
        if sort_by not in allowed_sort:
            raise ValueError(f"sort_by must be one of: {sorted(allowed_sort)}")
        if sort_order not in {"asc", "desc"}:
            raise ValueError("sort_order must be 'asc' or 'desc'")

        limit = max(1, min(limit, 1000))
        offset = max(0, offset)

        clauses: list[str] = []
        warnings: list[str] = []

        created_after = _to_epoch_from_iso(created_after_iso_utc)
        if created_after is not None:
            clauses.append(f"created_timestamp >= {int(created_after)}")

        created_before = _to_epoch_from_iso(created_before_iso_utc)
        if created_before is not None:
            clauses.append(f"created_timestamp <= {int(created_before)}")

        if size_min is not None:
            clauses.append(f"size >= {size_min}")
        if size_max is not None:
            clauses.append(f"size <= {size_max}")

        where = f" where {' and '.join(clauses)}" if clauses else ""
        query = f"files from {dataset_did}{where}"

        client = _client()
        need_metadata = (
            include_metadata
            or events_min is not None
            or events_max is not None
            or run_min is not None
            or run_max is not None
            or subrun_min is not None
            or subrun_max is not None
            or sort_by in {"run", "subrun", "n_events"}
        )

        rows = list(
            client.query(
                query,
                with_metadata=need_metadata,
                with_provenance=False,
            )
        )

        if (subrun_min is not None or subrun_max is not None) and run_min is None and run_max is None:
            warnings.append(
                "subrun_min/subrun_max are interpreted across rs.first_subrun/rs.last_subrun only; "
                "because subrun numbers restart each run, pair subrun filters with run_min/run_max "
                "for precise semantics."
            )

        filtered_rows: list[dict[str, Any]] = []
        for row in rows:
            nevent = _metadata_int(row, "rse.nevent")
            first_run = _metadata_int(row, "rs.first_run")
            last_run = _metadata_int(row, "rs.last_run")
            first_subrun = _metadata_int(row, "rs.first_subrun")
            last_subrun = _metadata_int(row, "rs.last_subrun")

            if events_min is not None and (nevent is None or nevent < events_min):
                continue
            if events_max is not None and (nevent is None or nevent > events_max):
                continue

            if run_min is not None and (last_run is None or last_run < run_min):
                continue
            if run_max is not None and (first_run is None or first_run > run_max):
                continue

            if subrun_min is not None and (last_subrun is None or last_subrun < subrun_min):
                continue
            if subrun_max is not None and (first_subrun is None or first_subrun > subrun_max):
                continue

            filtered_rows.append(row)

        reverse = sort_order == "desc"

        def _sort_key(item: dict[str, Any]) -> tuple[bool, Any]:
            if sort_by == "created_timestamp":
                value = _as_int(item.get("created_timestamp"))
            elif sort_by == "size":
                value = _as_int(item.get("size"))
            elif sort_by == "name":
                value = item.get("name")
            elif sort_by == "n_events":
                value = _metadata_int(item, "rse.nevent")
            elif sort_by == "run":
                value = _metadata_int(item, "rs.first_run")
            else:  # subrun
                value = _metadata_int(item, "rs.first_subrun")
            return (value is None, value)

        filtered_rows.sort(key=_sort_key, reverse=reverse)
        paged_rows = filtered_rows[offset : offset + limit]

        results = [_file_record(r) for r in paged_rows]
        if not include_metadata:
            for r in results:
                r.pop("metadata", None)

        return {
            "dataset_did": dataset_did,
            "query": query,
            "applied_filters": {
                "created_after_iso_utc": created_after_iso_utc,
                "created_before_iso_utc": created_before_iso_utc,
                "size_min": size_min,
                "size_max": size_max,
                "events_min": events_min,
                "events_max": events_max,
                "events_field": "metadata.rse.nevent",
                "run_min": run_min,
                "run_max": run_max,
                "run_fields": ["metadata.rs.first_run", "metadata.rs.last_run"],
                "subrun_min": subrun_min,
                "subrun_max": subrun_max,
                "subrun_fields": ["metadata.rs.first_subrun", "metadata.rs.last_subrun"],
                "sort_by": sort_by,
                "sort_order": sort_order,
                "limit": limit,
                "offset": offset,
                "include_metadata": include_metadata,
            },
            "total_matches": len(filtered_rows),
            "returned": len(results),
            "results": results,
            "warnings": warnings,
        }

    @mcp.tool(description="Return server capabilities and safe-usage guidance.")
    def get_server_info() -> dict[str, Any]:
        return {
            "name": "metacat-readonly",
            "transport": "stdio",
            "read_only": True,
            "auth_mode": "no explicit token by default (environment-driven)",
            "write_tools_exposed": False,
            "notes": [
                "Uses metacat.webapi.MetaCatClient() and environment from mu2einit/muse setup ops.",
                "Count-based dataset filtering can be slow at broad scope.",
                "Use discover_datasets filters before expensive detail calls.",
                "Collaboration namespace naming uses 'mu2e' (never 'mu2').",
                "User-owned namespaces are typically <username> or <username>_*.",
            ],
            "tools": [
                "discover_datasets",
                "get_dataset_details",
                "query_dataset_files",
                "get_server_info",
            ],
        }

    return mcp


def main() -> None:
    _configure_logging()
    mcp = create_mcp_server()
    LOGGER.info("Starting metacat read-only MCP server over stdio")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
