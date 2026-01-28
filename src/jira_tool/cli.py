"""Command-line interface for JIRA tool."""

import click

from jira_tool.client import JiraClient
from jira_tool.commands.issue import issue


class Context:
    """CLI context object holding shared state."""
    
    def __init__(self):
        self.client: JiraClient | None = None
        self.debug: bool = False


@click.group()
@click.option(
    "--debug", is_flag=True, default=False, envvar="JIRA_DEBUG",
    help="Enable debug output on errors (show full stack traces and raw responses)",
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
def cli(ctx, debug: bool, base_url: str, email: str, token: str):
    """JIRA CLI Tool - Interact with JIRA Cloud API from the command line.

    Authentication can be provided via command-line options or environment variables:
    
    \b
    - JIRA_BASE_URL: Your JIRA instance URL
    - JIRA_EMAIL: Your JIRA account email
    - JIRA_API_TOKEN: Your JIRA API token
    
    Use --debug or set JIRA_DEBUG=1 for verbose error output.
    """
    ctx.obj = Context()
    ctx.obj.debug = debug
    ctx.obj.client = JiraClient(base_url=base_url, email=email, api_token=token)


# Register command groups
cli.add_command(issue)
