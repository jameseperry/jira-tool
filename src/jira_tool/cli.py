"""Command-line interface for JIRA tool."""

import os
import click

from jira_tool.client import JiraClient
from jira_tool.commands.issue import issue
from jira_tool.commands.field import field
from jira_tool.commands.component import component
from jira_tool.commands.board import board
from jira_tool.commands.plan import plan


class Context:
    """CLI context object holding shared state."""

    def __init__(self):
        self.client: JiraClient | None = None
        self.debug: bool = False
        self.dry_run: bool = False


@click.group()
@click.option(
    "--debug", is_flag=True, default=False, envvar="JIRA_DEBUG",
    help="Enable debug output on errors (show full stack traces and raw responses)",
)
@click.option(
    "--dry-run", is_flag=True, default=False, envvar="JIRA_TOOL_DRY_RUN",
    help="Preview changes without executing them (also set via JIRA_TOOL_DRY_RUN=1)",
)
@click.option(
    "--base-url",
    envvar="JIRA_BASE_URL",
    required=True,
    help="JIRA instance base URL (e.g., https://yourcompany.atlassian.net)",
)
@click.option(
    "--email",
    envvar="JIRA_EMAIL",
    required=True,
    help="JIRA account email address",
)
@click.option(
    "--token",
    envvar="JIRA_API_TOKEN",
    required=True,
    help="JIRA API token",
)
@click.pass_context
def cli(ctx, debug: bool, dry_run: bool, base_url: str, email: str, token: str):
    """JIRA CLI Tool - Interact with JIRA Cloud API from the command line.

    Authentication can be provided via command-line options or environment variables:

    \b
    - JIRA_BASE_URL: Your JIRA instance URL
    - JIRA_EMAIL: Your JIRA account email
    - JIRA_API_TOKEN: Your JIRA API token
    - JIRA_TOOL_DRY_RUN: Set to 1, true, or yes to enable dry-run mode globally

    Use --debug or set JIRA_DEBUG=1 for verbose error output.
    Use --dry-run or set JIRA_TOOL_DRY_RUN=1 to preview changes without executing them.
    """
    ctx.obj = Context()
    ctx.obj.debug = debug
    ctx.obj.dry_run = dry_run
    ctx.obj.client = JiraClient(base_url=base_url, email=email, api_token=token)


# Register command groups
cli.add_command(issue)
cli.add_command(field)
cli.add_command(component)
cli.add_command(board)
cli.add_command(plan)
