from __future__ import annotations

import csv
import io
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

LOGGER = logging.getLogger("dqm_mcp")

DEFAULT_DBNAME = "mu2e_dqm_prd"
DEFAULT_QE_NOCACHE_URL = "https://dbdata0vm.fnal.gov:9443/QE/mu2e/prod/app/SQ/query?"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_LIMIT = 100
DEFAULT_RECENT_DAYS = 10
DEFAULT_SCAN_LIMIT = 2000

READ_ONLY_INSTRUCTIONS = (
    "Read-only MCP server for Mu2e DQM metrics via Query Engine over HTTP. "
    "Always use nocache endpoint access semantics. "
    "Return structured JSON rows from dqm.sources, dqm.values, dqm.intervals, dqm.numbers, and dqm.limits."
)


@dataclass
class QEClient:
    base_url: str
    dbname: str
    timeout_seconds: int

    def query_csv(
        self,
        table: str,
        columns: str,
        where: list[str] | None = None,
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        params: list[tuple[str, str]] = [
            ("dbname", self.dbname),
            ("t", table),
            ("c", columns),
            ("f", "csv"),
        ]

        if where:
            for clause in where:
                params.append(("w", clause))
        if order:
            params.append(("o", order))
        if limit is not None:
            params.append(("l", str(limit)))

        response = requests.get(self.base_url, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()

        payload = response.text.strip()
        if not payload:
            return []

        reader = csv.DictReader(io.StringIO(payload))
        return list(reader)


def _configure_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("DQM_MCP_LOG_LEVEL", "INFO"),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_dt_user(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _normalize_limit(limit: int) -> int:
    if limit <= 0:
        raise ValueError("limit must be > 0")
    return limit


def _apply_offset(rows: list[dict[str, Any]], limit: int, offset: int) -> list[dict[str, Any]]:
    if offset < 0:
        raise ValueError("offset must be >= 0")
    return rows[offset : offset + limit]


def _build_qe_client() -> QEClient:
    base_url = os.environ.get("DQM_QE_BASE_URL", DEFAULT_QE_NOCACHE_URL)
    if ":8444/" in base_url:
        raise ValueError("DQM_QE_BASE_URL points to cache endpoint (:8444); nocache (:9443) is required")
    dbname = os.environ.get("DQM_QE_DBNAME", DEFAULT_DBNAME)
    timeout_seconds = int(os.environ.get("DQM_QE_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    return QEClient(base_url=base_url, dbname=dbname, timeout_seconds=timeout_seconds)


def _sources_by_id(client: QEClient, sids: set[int]) -> dict[int, dict[str, Any]]:
    if not sids:
        return {}
    out: dict[int, dict[str, Any]] = {}
    for sid in sids:
        rows = client.query_csv(
            "dqm.sources",
            columns="sid,process,stream,aggregation,version",
            where=[f"sid:eq:{sid}"],
            limit=1,
        )
        if rows:
            row = rows[0]
            out[sid] = {
                "sid": sid,
                "process": row.get("process"),
                "stream": row.get("stream"),
                "aggregation": row.get("aggregation"),
                "version": row.get("version"),
            }
    return out


def _values_by_id(client: QEClient, vids: set[int]) -> dict[int, dict[str, Any]]:
    if not vids:
        return {}
    out: dict[int, dict[str, Any]] = {}
    for vid in vids:
        rows = client.query_csv(
            "dqm.values",
            columns="vid,groupx,subgroup,namex",
            where=[f"vid:eq:{vid}"],
            limit=1,
        )
        if rows:
            row = rows[0]
            out[vid] = {
                "vid": vid,
                "groupx": row.get("groupx"),
                "subgroup": row.get("subgroup"),
                "namex": row.get("namex"),
            }
    return out


def _intervals_by_id(client: QEClient, iids: set[int]) -> dict[int, dict[str, Any]]:
    if not iids:
        return {}
    out: dict[int, dict[str, Any]] = {}
    for iid in iids:
        rows = client.query_csv(
            "dqm.intervals",
            columns="iid,sid,start_run,start_subrun,end_run,end_subrun,start_time,end_time",
            where=[f"iid:eq:{iid}"],
            limit=1,
        )
        if rows:
            row = rows[0]
            out[iid] = {
                "iid": iid,
                "sid": _parse_int(row.get("sid")),
                "start_run": _parse_int(row.get("start_run")),
                "start_subrun": _parse_int(row.get("start_subrun")),
                "end_run": _parse_int(row.get("end_run")),
                "end_subrun": _parse_int(row.get("end_subrun")),
                "start_time": row.get("start_time"),
                "end_time": row.get("end_time"),
            }
    return out


def create_mcp_server() -> FastMCP:
    client = _build_qe_client()
    mcp = FastMCP("dqm", instructions=READ_ONLY_INSTRUCTIONS)

    @mcp.tool(description="Get DQM MCP configuration and defaults.")
    def get_server_info() -> dict[str, Any]:
        return {
            "name": "dqm",
            "read_only": True,
            "transport": "stdio",
            "qe": {
                "base_url": client.base_url,
                "dbname": client.dbname,
                "timeout_seconds": client.timeout_seconds,
                "nocache_required": True,
            },
            "defaults": {
                "query_limit": DEFAULT_LIMIT,
                "recent_days": DEFAULT_RECENT_DAYS,
                "scan_limit": DEFAULT_SCAN_LIMIT,
            },
        }

    @mcp.tool(description="List DQM metric sources from dqm.sources.")
    def list_sources(
        process: str | None = None,
        stream: str | None = None,
        aggregation: str | None = None,
        version: str | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit = _normalize_limit(limit)

        where: list[str] = []
        if process:
            where.append(f"process:eq:{process}")
        if stream:
            where.append(f"stream:eq:{stream}")
        if aggregation:
            where.append(f"aggregation:eq:{aggregation}")
        if version:
            where.append(f"version:eq:{version}")

        rows = client.query_csv(
            "dqm.sources",
            columns="sid,process,stream,aggregation,version",
            where=where or None,
            order="sid",
            limit=max(limit + offset, DEFAULT_LIMIT),
        )

        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "sid": _parse_int(row.get("sid")),
                    "process": row.get("process"),
                    "stream": row.get("stream"),
                    "aggregation": row.get("aggregation"),
                    "version": row.get("version"),
                }
            )

        paged = _apply_offset(out, limit, offset)
        return {
            "filters": {
                "process": process,
                "stream": stream,
                "aggregation": aggregation,
                "version": version,
                "limit": limit,
                "offset": offset,
            },
            "returned": len(paged),
            "results": paged,
        }

    @mcp.tool(description="List unique source versions, optionally filtered by process/stream/aggregation.")
    def list_versions(
        process: str | None = None,
        stream: str | None = None,
        aggregation: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        limit = _normalize_limit(limit)

        where: list[str] = []
        if process:
            where.append(f"process:eq:{process}")
        if stream:
            where.append(f"stream:eq:{stream}")
        if aggregation:
            where.append(f"aggregation:eq:{aggregation}")

        rows = client.query_csv(
            "dqm.sources",
            columns="sid,process,stream,aggregation,version",
            where=where or None,
            order="sid",
            limit=max(limit * 3, DEFAULT_LIMIT),
        )

        versions = sorted({row.get("version") for row in rows if row.get("version") is not None})
        return {
            "filters": {
                "process": process,
                "stream": stream,
                "aggregation": aggregation,
            },
            "version_count": len(versions),
            "versions": versions[:limit],
            "sources_examined": len(rows),
        }

    @mcp.tool(description="List DQM value names from dqm.values.")
    def list_values(
        groupx: str | None = None,
        subgroup: str | None = None,
        namex: str | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit = _normalize_limit(limit)

        where: list[str] = []
        if groupx:
            where.append(f"groupx:eq:{groupx}")
        if subgroup:
            where.append(f"subgroup:eq:{subgroup}")
        if namex:
            where.append(f"namex:eq:{namex}")

        rows = client.query_csv(
            "dqm.values",
            columns="vid,groupx,subgroup,namex",
            where=where or None,
            order="vid",
            limit=max(limit + offset, DEFAULT_LIMIT),
        )

        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "vid": _parse_int(row.get("vid")),
                    "groupx": row.get("groupx"),
                    "subgroup": row.get("subgroup"),
                    "namex": row.get("namex"),
                }
            )

        paged = _apply_offset(out, limit, offset)
        return {
            "filters": {
                "groupx": groupx,
                "subgroup": subgroup,
                "namex": namex,
                "limit": limit,
                "offset": offset,
            },
            "returned": len(paged),
            "results": paged,
        }

    @mcp.tool(description="List DQM intervals with run/subrun or time filters.")
    def list_intervals(
        sid: int | None = None,
        run: int | None = None,
        subrun: int | None = None,
        start_time_after_iso_utc: str | None = None,
        end_time_before_iso_utc: str | None = None,
        recent_days: int | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        newest_first: bool = True,
    ) -> dict[str, Any]:
        limit = _normalize_limit(limit)

        where: list[str] = []
        if sid is not None:
            where.append(f"sid:eq:{sid}")
        if run is not None:
            where.append(f"start_run:le:{run}")
            where.append(f"end_run:ge:{run}")
        if subrun is not None:
            where.append(f"start_subrun:le:{subrun}")
            where.append(f"end_subrun:ge:{subrun}")

        if recent_days is not None:
            recent_start = datetime.now(timezone.utc) - timedelta(days=recent_days)
            where.append(f"end_time:ge:{recent_start.strftime('%Y-%m-%dT%H:%M:%S%z')}")

        if start_time_after_iso_utc:
            dt = _parse_dt_user(start_time_after_iso_utc)
            where.append(f"end_time:ge:{dt.strftime('%Y-%m-%dT%H:%M:%S%z')}")

        if end_time_before_iso_utc:
            dt = _parse_dt_user(end_time_before_iso_utc)
            where.append(f"start_time:le:{dt.strftime('%Y-%m-%dT%H:%M:%S%z')}")

        rows = client.query_csv(
            "dqm.intervals",
            columns="iid,sid,start_run,start_subrun,end_run,end_subrun,start_time,end_time",
            where=where or None,
            order="-iid" if newest_first else "iid",
            limit=max(limit + offset, DEFAULT_LIMIT),
        )

        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "iid": _parse_int(row.get("iid")),
                    "sid": _parse_int(row.get("sid")),
                    "start_run": _parse_int(row.get("start_run")),
                    "start_subrun": _parse_int(row.get("start_subrun")),
                    "end_run": _parse_int(row.get("end_run")),
                    "end_subrun": _parse_int(row.get("end_subrun")),
                    "start_time": row.get("start_time"),
                    "end_time": row.get("end_time"),
                }
            )

        paged = _apply_offset(out, limit, offset)
        return {
            "filters": {
                "sid": sid,
                "run": run,
                "subrun": subrun,
                "start_time_after_iso_utc": start_time_after_iso_utc,
                "end_time_before_iso_utc": end_time_before_iso_utc,
                "recent_days": recent_days,
                "limit": limit,
                "offset": offset,
                "newest_first": newest_first,
            },
            "returned": len(paged),
            "results": paged,
        }

    @mcp.tool(
        description=(
            "Query DQM metrics from dqm.numbers (default) or dqm.limits with optional source/value expansion. "
            "Defaults to recent_days=10 and limit=100."
        )
    )
    def query_metrics(
        metric_table: str = "numbers",
        sid: int | None = None,
        vid: int | None = None,
        process: str | None = None,
        stream: str | None = None,
        aggregation: str | None = None,
        version: str | None = None,
        groupx: str | None = None,
        subgroup: str | None = None,
        namex: str | None = None,
        run: int | None = None,
        subrun: int | None = None,
        start_time_after_iso_utc: str | None = None,
        end_time_before_iso_utc: str | None = None,
        recent_days: int = DEFAULT_RECENT_DAYS,
        sort_by: str = "end_time",
        sort_order: str = "desc",
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        expand_ids: bool = True,
        scan_limit: int = DEFAULT_SCAN_LIMIT,
    ) -> dict[str, Any]:
        metric_table = metric_table.strip().lower()
        if metric_table not in {"numbers", "limits"}:
            raise ValueError("metric_table must be 'numbers' or 'limits'")
        if sort_order not in {"asc", "desc"}:
            raise ValueError("sort_order must be 'asc' or 'desc'")

        allowed_sort = {
            "numbers": {"nid", "valuex", "sigma", "code", "start_run", "end_run", "start_subrun", "end_subrun", "start_time", "end_time"},
            "limits": {"lid", "llimit", "ulimit", "sigma", "alarmcode", "start_run", "end_run", "start_subrun", "end_subrun", "start_time", "end_time"},
        }
        if sort_by not in allowed_sort[metric_table]:
            raise ValueError(f"sort_by is not valid for {metric_table}")

        limit = _normalize_limit(limit)
        if offset < 0:
            raise ValueError("offset must be >= 0")
        if scan_limit <= 0:
            raise ValueError("scan_limit must be > 0")

        source_where: list[str] = []
        if sid is not None:
            source_where.append(f"sid:eq:{sid}")
        if process:
            source_where.append(f"process:eq:{process}")
        if stream:
            source_where.append(f"stream:eq:{stream}")
        if aggregation:
            source_where.append(f"aggregation:eq:{aggregation}")
        if version:
            source_where.append(f"version:eq:{version}")

        source_rows = client.query_csv(
            "dqm.sources",
            columns="sid,process,stream,aggregation,version",
            where=source_where or None,
            order="sid",
            limit=scan_limit,
        )
        allowed_sids = {_parse_int(r.get("sid")) for r in source_rows}
        allowed_sids.discard(None)

        value_where: list[str] = []
        if vid is not None:
            value_where.append(f"vid:eq:{vid}")
        if groupx:
            value_where.append(f"groupx:eq:{groupx}")
        if subgroup:
            value_where.append(f"subgroup:eq:{subgroup}")
        if namex:
            value_where.append(f"namex:eq:{namex}")

        value_rows = client.query_csv(
            "dqm.values",
            columns="vid,groupx,subgroup,namex",
            where=value_where or None,
            order="vid",
            limit=scan_limit,
        )
        allowed_vids = {_parse_int(r.get("vid")) for r in value_rows}
        allowed_vids.discard(None)

        interval_where: list[str] = []
        if run is not None:
            interval_where.append(f"start_run:le:{run}")
            interval_where.append(f"end_run:ge:{run}")
        if subrun is not None:
            interval_where.append(f"start_subrun:le:{subrun}")
            interval_where.append(f"end_subrun:ge:{subrun}")

        if recent_days is not None:
            recent_start = datetime.now(timezone.utc) - timedelta(days=recent_days)
            interval_where.append(f"end_time:ge:{recent_start.strftime('%Y-%m-%dT%H:%M:%S%z')}")

        if start_time_after_iso_utc:
            dt = _parse_dt_user(start_time_after_iso_utc)
            interval_where.append(f"end_time:ge:{dt.strftime('%Y-%m-%dT%H:%M:%S%z')}")

        if end_time_before_iso_utc:
            dt = _parse_dt_user(end_time_before_iso_utc)
            interval_where.append(f"start_time:le:{dt.strftime('%Y-%m-%dT%H:%M:%S%z')}")

        interval_rows = client.query_csv(
            "dqm.intervals",
            columns="iid,sid,start_run,start_subrun,end_run,end_subrun,start_time,end_time",
            where=interval_where or None,
            order="-iid",
            limit=scan_limit,
        )

        allowed_iids = {_parse_int(r.get("iid")) for r in interval_rows}
        allowed_iids.discard(None)

        metric_cols = "nid,sid,iid,vid,valuex,sigma,code" if metric_table == "numbers" else "lid,sid,iid,vid,llimit,ulimit,sigma,alarmcode"
        metric_pk = "nid" if metric_table == "numbers" else "lid"

        metric_rows = client.query_csv(
            f"dqm.{metric_table}",
            columns=metric_cols,
            order=f"-{metric_pk}",
            limit=scan_limit,
        )

        interval_map: dict[int, dict[str, Any]] = {}
        for row in interval_rows:
            iid_val = _parse_int(row.get("iid"))
            if iid_val is None:
                continue
            interval_map[iid_val] = {
                "iid": iid_val,
                "sid": _parse_int(row.get("sid")),
                "start_run": _parse_int(row.get("start_run")),
                "start_subrun": _parse_int(row.get("start_subrun")),
                "end_run": _parse_int(row.get("end_run")),
                "end_subrun": _parse_int(row.get("end_subrun")),
                "start_time": row.get("start_time"),
                "end_time": row.get("end_time"),
            }

        source_map = {sidv: item for sidv, item in _sources_by_id(client, {s for s in allowed_sids if s is not None}).items()}
        value_map = {vidv: item for vidv, item in _values_by_id(client, {v for v in allowed_vids if v is not None}).items()}

        results: list[dict[str, Any]] = []
        for row in metric_rows:
            sid_val = _parse_int(row.get("sid"))
            vid_val = _parse_int(row.get("vid"))
            iid_val = _parse_int(row.get("iid"))

            if sid_val is None or vid_val is None or iid_val is None:
                continue
            if sid_val not in allowed_sids:
                continue
            if vid_val not in allowed_vids:
                continue
            if iid_val not in allowed_iids:
                continue

            interval = interval_map.get(iid_val)
            if interval is None:
                interval = _intervals_by_id(client, {iid_val}).get(iid_val)
                if interval is not None:
                    interval_map[iid_val] = interval

            entry: dict[str, Any] = {
                "sid": sid_val,
                "vid": vid_val,
                "iid": iid_val,
            }

            if metric_table == "numbers":
                entry["nid"] = _parse_int(row.get("nid"))
                entry["valuex"] = _parse_float(row.get("valuex"))
                entry["sigma"] = _parse_float(row.get("sigma"))
                entry["code"] = _parse_int(row.get("code"))
            else:
                entry["lid"] = _parse_int(row.get("lid"))
                entry["llimit"] = _parse_float(row.get("llimit"))
                entry["ulimit"] = _parse_float(row.get("ulimit"))
                entry["sigma"] = _parse_float(row.get("sigma"))
                entry["alarmcode"] = _parse_int(row.get("alarmcode"))

            if interval is not None:
                entry["interval"] = interval
            if expand_ids:
                if sid_val in source_map:
                    entry["source"] = source_map[sid_val]
                if vid_val in value_map:
                    entry["value"] = value_map[vid_val]

            results.append(entry)

        reverse = sort_order == "desc"

        def sort_key(item: dict[str, Any]) -> Any:
            if sort_by in item:
                return item.get(sort_by)
            interval = item.get("interval", {})
            v = interval.get(sort_by)
            if sort_by in {"start_time", "end_time"}:
                return _parse_dt(v) or datetime.fromtimestamp(0, tz=timezone.utc)
            return v

        results.sort(key=sort_key, reverse=reverse)
        paged = _apply_offset(results, limit, offset)

        warnings: list[str] = []
        if len(metric_rows) >= scan_limit:
            warnings.append(
                "scan_limit reached; consider increasing scan_limit for very selective filters"
            )

        return {
            "metric_table": metric_table,
            "filters": {
                "sid": sid,
                "vid": vid,
                "process": process,
                "stream": stream,
                "aggregation": aggregation,
                "version": version,
                "groupx": groupx,
                "subgroup": subgroup,
                "namex": namex,
                "run": run,
                "subrun": subrun,
                "start_time_after_iso_utc": start_time_after_iso_utc,
                "end_time_before_iso_utc": end_time_before_iso_utc,
                "recent_days": recent_days,
                "sort_by": sort_by,
                "sort_order": sort_order,
                "limit": limit,
                "offset": offset,
                "expand_ids": expand_ids,
                "scan_limit": scan_limit,
            },
            "counts": {
                "candidate_sources": len(allowed_sids),
                "candidate_values": len(allowed_vids),
                "candidate_intervals": len(allowed_iids),
                "scanned_metric_rows": len(metric_rows),
                "matched_rows": len(results),
                "returned_rows": len(paged),
            },
            "warnings": warnings,
            "results": paged,
        }

    return mcp


def main() -> None:
    _configure_logging()
    mcp = create_mcp_server()
    LOGGER.info("Starting dqm MCP server over stdio")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
