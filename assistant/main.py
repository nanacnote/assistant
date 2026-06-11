"""CLI entrypoint for the assistant runtime."""

from __future__ import annotations

import argparse
import asyncio
import logging

from dotenv import find_dotenv, load_dotenv

from assistant.config import AssistantSettings, SettingsError
from assistant.runtime import AssistantRuntime

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Create the assistant CLI parser."""
    parser = argparse.ArgumentParser(prog="assistant")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate Matrix and LLM configuration, then exit",
    )
    return parser


def main() -> None:
    """Run the assistant runtime."""
    env_file = find_dotenv(usecwd=True)
    if env_file:
        load_dotenv(env_file, override=False)

    args = build_parser().parse_args()
    settings = AssistantSettings.from_env()
    try:
        settings.validate()
    except SettingsError as exc:
        raise SystemExit(str(exc)) from exc

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.check_config:
        logger.info("assistant configuration is valid")
        return

    logger.debug(
        "starting with log_level=%s event_workers=%d agent_max_steps=%d",
        settings.log_level,
        settings.event_workers,
        settings.agent_max_steps,
    )
    runtime = AssistantRuntime(settings)

    async def run_forever() -> None:
        await runtime.start()
        logger.info("assistant runtime started and listening for Matrix events")
        try:
            await asyncio.Event().wait()
        finally:
            await runtime.stop()

    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
