"""CLI entry point for dji-flightlog-parser.

Drop-in compatible with the Rust dji-log CLI used by Loggflyt.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from .parser import DJILog
from .export.json_export import export_json, export_json_raw
from .export.geojson import export_geojson
from .export.kml import export_kml
from .export.csv_export import export_csv


@click.command()
@click.argument("filepath", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default=None, help="JSON output path (stdout if omitted)")
@click.option("-a", "--api-key", type=str, default=None, help="DJI API key for v13+ decryption")
@click.option("-r", "--raw", is_flag=True, default=False, help="Export raw records instead of frames")
@click.option("--geojson", type=click.Path(), default=None, help="GeoJSON output path")
@click.option("--kml", type=click.Path(), default=None, help="KML output path")
@click.option("--csv", type=click.Path(), default=None, help="CSV output path")
@click.option("--extended", is_flag=True, default=False, help="Include extended record types in output")
@click.option("--api-custom-department", type=int, default=None, help="Override department for keychain request")
@click.option("--api-custom-version", type=int, default=None, help="Override version for keychain request")
@click.option("--no-cache", is_flag=True, default=False, help="Disable keychain caching")
@click.option("-v", "--verbose", is_flag=True, default=False, help="Enable verbose logging")
def main(
    filepath: str,
    output: str | None,
    api_key: str | None,
    raw: bool,
    geojson: str | None,
    kml: str | None,
    csv: str | None,
    extended: bool,
    api_custom_department: int | None,
    api_custom_version: int | None,
    no_cache: bool,
    verbose: bool,
) -> None:
    """Parse a DJI flight log file."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    log = DJILog.from_file(filepath)

    keychains = None
    if log.version >= 13:
        if not api_key:
            click.echo("Error: API key is required for version 13+", err=True)
            sys.exit(1)

        keychains = log.fetch_keychains(
            api_key,
            use_cache=not no_cache,
            department=api_custom_department,
            version=api_custom_version,
        )

    records = log.records(keychains)
    log.enrich_details(records)
    frames = log.frames(keychains)

    # JSON export
    if raw:
        json_str = export_json_raw(log.version, log.details, records, output)
    else:
        json_str = export_json(log.version, log.details, frames, output)

    if not output:
        click.echo(json_str)

    # Additional exports
    if geojson:
        export_geojson(log.details, frames, geojson)

    if kml:
        export_kml(log.details, frames, kml)

    if csv:
        export_csv(frames, csv)


if __name__ == "__main__":
    main()
