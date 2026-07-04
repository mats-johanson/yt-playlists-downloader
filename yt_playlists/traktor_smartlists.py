"""Auto-generate Traktor Smart Playlists mirroring `Synced Music/<folder>`.

Why: Traktor 3.x folder-browser views don't honor sort-by-column (confirmed
NI community bug across 3.x and Pro 4). Smart Playlists DO sort. So we mirror
each on-disk folder as a Smart Playlist with a `$FILEPATH % "<folder>"`
contains-rule. Traktor auto-populates from that rule on every launch — no
ongoing sync needed.

Idempotent: re-running adds only missing playlists; existing ones are left
intact. The user can rename or alter rules manually without us clobbering.

Placement: matches the parent FOLDER NODE of an "anchor" smartlist the user
already created (the first user-made smartlist found in the file). Falls back
to a top-level "Sync" FOLDER if no anchor is present.
"""

from __future__ import annotations

import os
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from rich.console import Console


def sync_smartlists(
    *,
    console: Console,
    nml_path: Path,
    synced_root: Path,
) -> int:
    if not nml_path.exists():
        console.print(f"[red]collection.nml not found:[/] {nml_path}")
        return 1
    if not synced_root.exists():
        console.print(f"[red]Synced root not found:[/] {synced_root}")
        return 1

    folder_names = sorted(
        d.name for d in synced_root.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )
    if not folder_names:
        console.print("[yellow]No folders under Synced root.[/]")
        return 0

    bak = nml_path.with_suffix(
        nml_path.suffix + f".bak.smartlists.{time.strftime('%Y%m%d-%H%M%S')}"
    )
    bak.write_bytes(nml_path.read_bytes())
    console.print(f"[dim]Backup → {bak.name}[/]")

    tree = ET.parse(nml_path)
    root = tree.getroot()

    container_subnodes = _find_or_create_container(root, console)
    if container_subnodes is None:
        console.print("[red]Couldn't find or create a container FOLDER NODE.[/]")
        return 1

    existing_names = {
        n.attrib.get("NAME", "")
        for n in container_subnodes.findall("NODE")
        if n.attrib.get("TYPE") == "SMARTLIST"
    }

    created = 0
    for name in folder_names:
        if name in existing_names:
            continue
        container_subnodes.append(_make_smartlist_node(name))
        created += 1

    # Keep the SUBNODES COUNT attribute consistent. Traktor relies on it for
    # display; mismatches can show stale child counts in the sidebar.
    container_subnodes.attrib["COUNT"] = str(len(container_subnodes.findall("NODE")))

    tmp = nml_path.with_suffix(nml_path.suffix + ".tmp")
    tree.write(tmp, encoding="utf-8", xml_declaration=True)
    try:
        ET.parse(tmp)
    except ET.ParseError as e:
        tmp.unlink(missing_ok=True)
        console.print(f"[red]ABORT: produced invalid XML — {e}[/]")
        return 1
    os.replace(tmp, nml_path)

    console.print(
        f"[green]Smartlists:[/]            created {created} new "
        f"(skipped {len(folder_names) - created} already present)"
    )
    return 0


def _find_or_create_container(
    root: ET.Element, console: Console
) -> ET.Element | None:
    """Locate the SUBNODES of the FOLDER NODE that should hold our smartlists.

    Strategy: find the first SMARTLIST anchor under PLAYLISTS that isn't one
    of Traktor's three built-ins. That tells us which FOLDER the user is
    grouping their own smartlists under. We add to that FOLDER. If no user
    smartlist exists, fall back to creating a top-level `Sync` FOLDER under
    the $ROOT FOLDER's SUBNODES.
    """
    BUILTIN_NAMES = {"Played in this session", "Recently added", "Top rated tracks"}

    parent_map: dict = {id(c): p for p in root.iter() for c in p}

    def parent_of(node: ET.Element) -> ET.Element | None:
        return parent_map.get(id(node))

    # Pass 1: look for an anchor smartlist
    for node in root.iter("NODE"):
        if node.attrib.get("TYPE") != "SMARTLIST":
            continue
        if node.attrib.get("NAME") in BUILTIN_NAMES:
            continue
        # Walk up: parent is SUBNODES, grandparent is the FOLDER NODE
        subnodes = parent_of(node)
        if subnodes is None or subnodes.tag != "SUBNODES":
            continue
        folder_node = parent_of(subnodes)
        if folder_node is None or folder_node.attrib.get("TYPE") != "FOLDER":
            continue
        console.print(
            f"[dim]Adding to existing FOLDER {folder_node.attrib.get('NAME')!r} "
            f"(anchor: {node.attrib.get('NAME')!r})[/]"
        )
        return subnodes

    # Pass 2: create a fresh `Sync` FOLDER at top level
    for node in root.iter("NODE"):
        if node.attrib.get("NAME") == "$ROOT" and node.attrib.get("TYPE") == "FOLDER":
            root_subnodes = node.find("SUBNODES")
            if root_subnodes is None:
                continue
            new_folder = ET.SubElement(
                root_subnodes, "NODE", {"TYPE": "FOLDER", "NAME": "Sync"}
            )
            new_subnodes = ET.SubElement(new_folder, "SUBNODES", {"COUNT": "0"})
            root_subnodes.attrib["COUNT"] = str(len(root_subnodes.findall("NODE")))
            console.print("[dim]Created new top-level FOLDER 'Sync' for smartlists.[/]")
            return new_subnodes
    return None


def _make_smartlist_node(name: str) -> ET.Element:
    """Build the XML for one Smart Playlist matching the user's template.

    Format mirrors Traktor's own:
      <NODE TYPE="SMARTLIST" NAME="<name>">
        <SMARTLIST UUID="<hex>">
          <SEARCH_EXPRESSION VERSION="1" QUERY="$FILEPATH % &quot;<name>&quot;" />
        </SMARTLIST>
      </NODE>

    The rule is folder-name-contains rather than full-path qualified —
    matches what the user picked when they created `Astumine` by hand.
    Folder names under Synced Music are unique enough that the contains
    match doesn't over-include in practice.
    """
    node = ET.Element("NODE", {"TYPE": "SMARTLIST", "NAME": name})
    sm = ET.SubElement(node, "SMARTLIST", {"UUID": uuid.uuid4().hex})
    # XML escaping of the quotes inside QUERY is automatic via ET.
    ET.SubElement(
        sm,
        "SEARCH_EXPRESSION",
        {"VERSION": "1", "QUERY": f'$FILEPATH % "{name}"'},
    )
    return node
