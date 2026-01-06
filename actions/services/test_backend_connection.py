#!/usr/bin/env python3
"""Small utility to test backend (API) connectivity and run a few sample queries.

Place this file in the repo and run it from the project root. It will import
the existing `BackendService` implementation and call several read-only
endpoints to verify the backend is reachable and returning expected JSON.

Examples (PowerShell):

    # Basic test using .env values
    python .\actions\services\test_backend_connection.py

    # Provide explicit base URL and API key
    python .\actions\services\test_backend_connection.py --base-url http://localhost:8000 --api-key secret

    # Also fetch demandes for a username
    python .\actions\services\test_backend_connection.py --username alice

"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


def setup_import_path() -> None:
    """Ensure the repository root is on sys.path so we can import actions.* modules.

    This script is intended to be run from the project root. If you run it
    from elsewhere, this helper will add the repo root (two levels up from
    this file) to sys.path so imports work reliably.
    """
    here = os.path.abspath(os.path.dirname(__file__))
    repo_root = os.path.abspath(os.path.join(here, "..", ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


def pretty_print(title: str, obj: Any) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)
    try:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    except Exception:
        print(repr(obj))


def main() -> int:
    setup_import_path()

    # Local import after sys.path is set
    try:
        from actions.services.ddr_service import BackendService
    except Exception as e:
        print(f"❌ Unable to import BackendService: {e}")
        return 2

    parser = argparse.ArgumentParser(description="Test backend API connectivity and sample queries")
    parser.add_argument("--base-url", help="Backend base URL (overrides .env)")
    parser.add_argument("--api-key", help="API key to use for requests (overrides .env)")
    parser.add_argument("--username", help="Username to fetch demandes for (optional)")
    parser.add_argument("--demande-id", type=int, help="Demande id to fetch (optional)")
    parser.add_argument("--poste-id", type=int, help="Poste id to fetch (optional)")
    parser.add_argument("--create-demo", action="store_true", help="(Optional) try to create a demo demande (careful: writes data)")
    args = parser.parse_args()

    service = BackendService(base_url=args.base_url, api_key=args.api_key)

    ok = False

    # 1) Get postes
    postes = service.get_postes()
    pretty_print("Postes (sample)", postes[:5] if isinstance(postes, list) else postes)
    if postes is not None:
        ok = True

    # 2) Get directions
    directions = service.get_directions()
    pretty_print("Directions (sample)", directions[:5] if isinstance(directions, list) else directions)
    if directions is not None:
        ok = True

    # 3) Get users
    users = service.get_users()
    pretty_print("Users (sample)", users[:5] if isinstance(users, list) else users)
    if users is not None:
        ok = True

    # 4) Get motifs
    motifs = service.get_motif_demandes()
    pretty_print("Motifs (sample)", motifs[:10] if isinstance(motifs, list) else motifs)
    if motifs is not None:
        ok = True

    # 5) Optional: demandes by username
    if args.username:
        demandes = service.get_demandes_by_username(args.username)
        pretty_print(f"Demandes for username={args.username}", demandes)
        if demandes is not None:
            ok = True

    # 6) Optional: fetch specific demande
    if args.demande_id:
        demande = service.get_demande_by_id(args.demande_id)
        pretty_print(f"Demande id={args.demande_id}", demande)
        if demande is not None:
            ok = True

    # 7) Optional: fetch specific poste
    if args.poste_id:
        poste = service.get_poste_by_id(args.poste_id)
        pretty_print(f"Poste id={args.poste_id}", poste)
        if poste is not None:
            ok = True

    # 8) Optional: try to create a demo demande (write operation)
    if args.create_demo:
        demo = {
            "Titre": "Test DDR from script",
            "Description": "Ceci est une demande de test créée par test_backend_connection.py",
            "CreatedAt": None
        }
        created = service.create_demande(demo)
        pretty_print("Create demo demande result", created)
        if created is not None:
            ok = True

    print("\nSummary: backend reachable" if ok else "\nSummary: backend not reachable or returned errors")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
