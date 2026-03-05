from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from mcp.server.fastmcp import FastMCP

LOGGER = logging.getLogger("sim_epochs_mcp")


@dataclass
class CatalogSnapshot:
    mtime_ns: int
    epochs_to_datasets: dict[str, list[str]]


class CatalogStore:
    """File-backed catalog cache with mtime invalidation."""

    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._lock = Lock()
        self._snapshot: CatalogSnapshot | None = None

    def load(self) -> CatalogSnapshot:
        with self._lock:
            stat = self.catalog_path.stat()
            if self._snapshot and self._snapshot.mtime_ns == stat.st_mtime_ns:
                return self._snapshot

            with self.catalog_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)

            normalized = _normalize_catalog(payload)
            snapshot = CatalogSnapshot(mtime_ns=stat.st_mtime_ns, epochs_to_datasets=normalized)
            self._snapshot = snapshot
            return snapshot


def _normalize_catalog(payload: Any) -> dict[str, list[str]]:
    if isinstance(payload, dict) and "epochs" in payload:
        epochs = payload["epochs"]
        if not isinstance(epochs, list):
            raise ValueError("catalog['epochs'] must be a list")
        result: dict[str, list[str]] = {}
        for item in epochs:
            if not isinstance(item, dict):
                raise ValueError("each item in catalog['epochs'] must be an object")
            name = item.get("name")
            datasets = item.get("datasets", [])
            if not isinstance(name, str) or not name.strip():
                raise ValueError("epoch name must be a non-empty string")
            if not isinstance(datasets, list) or not all(isinstance(d, str) for d in datasets):
                raise ValueError(f"datasets for epoch '{name}' must be a list of strings")
            result[name] = sorted(set(datasets))
        return result

    if isinstance(payload, dict):
        result = {}
        for name, datasets in payload.items():
            if not isinstance(name, str):
                raise ValueError("catalog keys must be strings")
            if not isinstance(datasets, list) or not all(isinstance(d, str) for d in datasets):
                raise ValueError(f"datasets for epoch '{name}' must be a list of strings")
            result[name] = sorted(set(datasets))
        return result

    raise ValueError("catalog JSON must be an object")


def _default_catalog_path() -> Path:
    env_path = os.environ.get("SIM_EPOCHS_FILE")
    if env_path:
        return Path(env_path).expanduser().resolve()

    package_root = Path(__file__).resolve().parents[2]
    return package_root / "data" / "sim_catalog.json"


def _configure_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("SIM_EPOCHS_LOG_LEVEL", "INFO"),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def create_mcp_server() -> FastMCP:
    catalog_path = _default_catalog_path()
    store = CatalogStore(catalog_path=catalog_path)

    mcp = FastMCP(
        "sim-epochs",
        instructions=(
            "Answer simulation epoch and dataset questions from the configured catalog file. "
            "Use get_simulation_epochs() for epoch discovery and "
            "get_datasets_for_epoch(epoch) for details."
        ),
    )

    @mcp.tool(description="Return the list of known simulation epochs from the catalog file.")
    def get_simulation_epochs() -> dict[str, Any]:
        snapshot = store.load()
        return {
            "catalog_file": str(catalog_path),
            "epochs": sorted(snapshot.epochs_to_datasets.keys()),
            "count": len(snapshot.epochs_to_datasets),
        }

    @mcp.tool(description="Return dataset names for a given simulation epoch.")
    def get_datasets_for_epoch(epoch: str) -> dict[str, Any]:
        snapshot = store.load()
        datasets = snapshot.epochs_to_datasets.get(epoch)
        if datasets is None:
            return {
                "catalog_file": str(catalog_path),
                "epoch": epoch,
                "found": False,
                "available_epochs": sorted(snapshot.epochs_to_datasets.keys()),
                "message": f"Unknown epoch: {epoch}",
            }
        return {
            "catalog_file": str(catalog_path),
            "epoch": epoch,
            "found": True,
            "datasets": datasets,
            "count": len(datasets),
        }

    return mcp


def main() -> None:
    _configure_logging()
    mcp = create_mcp_server()
    LOGGER.info("Starting sim-epochs MCP server over stdio")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
