import argparse
import logging
import sys
from pathlib import Path
from typing import List

import crayons

from ssis_validator import Mode, ValidationPipeline

logger = logging.getLogger(__name__)


def determine_mode(args: List[str]) -> Mode:
    mode = None
    if args.repository and args.repository is not None:
        mode = Mode("Repository", [Path(args.projects[0])], True)
    elif args.projects is not None:
        mode = Mode("Directory", [Path(p) for p in args.projects], False)
    else:
        raise ValueError("Invalid argument provided")

    return mode


def print_mode_info(mode: Mode) -> None:
    print()
    if mode.is_repo:
        logger.info("o  Mode: Repository")
        logger.info(f"o  Looking for staged projects in {mode.directories[0]}")
    else:
        logger.info("o  Mode: Directory")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ssis_validator",
        description="Validates SSIS Package XML file to ensure consistent"
        "configuration per predefined specifications",
    )

    parser.add_argument(
        "-r",
        "--repository",
        action="store_true",
        help="Flag for whether validating staging of a Git repository",
    )

    parser.add_argument(
        "-p",
        "--project",
        action="append",
        required=True,
        help="Path to SSIS Projects",
        metavar="PROJECT_NAME",
    )

    args = parser.parse_args()

    mode = determine_mode(args)

    print_mode_info(mode)

    try:
        validation_pipeline = ValidationPipeline(mode)
        validation_pipeline.run()
        validation_pipeline.print_validation_result()
    except Exception as e:
        print()
        logger.exception(crayons.red(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
