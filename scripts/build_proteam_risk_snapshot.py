from __future__ import annotations

import argparse

from uci_points_model.pcs_client import CYCLE_SCOPE, CURRENT_SCOPE
from uci_points_model.proteam_risk import build_proteam_risk_dataset, write_proteam_risk_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Build bundled ProTeam risk snapshots from PCS.")
    parser.add_argument(
        "--scopes",
        nargs="+",
        default=[CURRENT_SCOPE, CYCLE_SCOPE],
        choices=[CURRENT_SCOPE, CYCLE_SCOPE],
        help="Risk-monitor scopes to scrape and snapshot.",
    )
    args = parser.parse_args()

    for scope in args.scopes:
        dataset = build_proteam_risk_dataset(scope=scope)
        path = write_proteam_risk_snapshot(dataset=dataset, scope=scope)
        print(f"{scope}: wrote {len(dataset)} rider rows to {path}")


if __name__ == "__main__":
    main()
