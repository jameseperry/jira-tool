"""Issue-related CLI commands.

This package contains all issue subcommands, organized into separate modules.
Shared utilities (FormatOption, decorators, helpers) are defined here.
"""

import json
import sys
from functools import wraps

import click

from jira_tool.client import JiraClient, JiraError
from jira_tool.formatting import (
    format_issues_compact,
    format_issues_csv,
    output_data,
)
from jira_tool.utils import (
    filter_custom_fields,
    simplify_issue,
    filter_fields,
    parse_fields_option,
    AVAILABLE_FIELDS,
    DEFAULT_FIELDS_GET,
    DEFAULT_FIELDS_SEARCH,
)


# =============================================================================
# Format Options Helper
# =============================================================================


class FormatOption(click.Option):
    """Custom option class for mutually exclusive format options."""

    def __init__(self, *args, **kwargs):
        self.mutually_exclusive = kwargs.pop("mutually_exclusive", [])
        super().__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        if self.name in opts:
            for other in self.mutually_exclusive:
                if other in opts:
                    raise click.UsageError(
                        f"--{self.name} is mutually exclusive with --{other}"
                    )
        return super().handle_parse_result(ctx, opts, args)


def format_options(func):
    """Decorator to add --json/--yaml/--csv/--list format options to a command."""
    func = click.option(
        "--human", "output_format",
        flag_value="text",
        default=True,
        cls=FormatOption,
        mutually_exclusive=["json", "yaml", "csv", "list"],
        help="Output as human-readable text (default)",
    )(func)
    func = click.option(
        "--list", "-l", "output_format",
        flag_value="list",
        cls=FormatOption,
        mutually_exclusive=["json", "yaml", "csv", "human"],
        help="Output only issue keys, one per line (for scripting)",
    )(func)
    func = click.option(
        "--csv", "output_format",
        flag_value="csv",
        cls=FormatOption,
        mutually_exclusive=["json", "yaml", "human", "list"],
        help="Output as CSV (for search results)",
    )(func)
    func = click.option(
        "--yaml", "output_format",
        flag_value="yaml",
        cls=FormatOption,
        mutually_exclusive=["json", "human", "csv", "list"],
        help="Output as YAML",
    )(func)
    func = click.option(
        "--json", "output_format",
        flag_value="json",
        cls=FormatOption,
        mutually_exclusive=["yaml", "human", "csv", "list"],
        help="Output as JSON",
    )(func)
    return func


# =============================================================================
# Error Handling Decorator
# =============================================================================


def handle_api_errors(func):
    """Decorator to catch and display API errors cleanly."""
    @wraps(func)
    def wrapper(ctx, *args, **kwargs):
        try:
            return func(ctx, *args, **kwargs)
        except JiraError as e:
            # For 400 errors with field errors, try to get field name mappings
            field_name_map = None
            if e.status_code == 400 and e.response and "errors" in e.response:
                try:
                    # Fetch field definitions to translate IDs to names
                    fields = ctx.client.get_fields()
                    field_name_map = {f.get("id", ""): f.get("name", "") for f in fields}
                except Exception:
                    pass  # Silently fail - we'll just show the field IDs
            
            click.echo(click.style(e.format_error(field_name_map), fg="red"), err=True)
            
            # Show additional debug info if --debug flag is set
            if ctx.debug:
                click.echo("", err=True)
                click.echo(click.style("Debug Information:", fg="yellow", bold=True), err=True)
                click.echo(click.style("─" * 50, fg="yellow"), err=True)
                
                # Raw response
                if e.response:
                    click.echo(click.style("Raw API Response:", fg="yellow"), err=True)
                    click.echo(json.dumps(e.response, indent=2, default=str), err=True)
                
                # Full response headers
                if e.response_headers:
                    click.echo(click.style("\nAll Response Headers:", fg="yellow"), err=True)
                    for k, v in sorted(e.response_headers.items()):
                        click.echo(f"  {k}: {v}", err=True)
                
                # Stack trace
                click.echo(click.style("\nStack Trace:", fg="yellow"), err=True)
                import traceback
                click.echo(traceback.format_exc(), err=True)
            
            sys.exit(1)
        except Exception as e:
            click.echo(click.style(f"Error: {e}", fg="red"), err=True)
            
            if ctx.debug:
                click.echo("", err=True)
                click.echo(click.style("Stack Trace:", fg="yellow", bold=True), err=True)
                import traceback
                click.echo(traceback.format_exc(), err=True)
            
            sys.exit(1)
    return wrapper


# =============================================================================
# JQL Query Builder
# =============================================================================


def build_jql_query(
    project: str | None = None,
    component: tuple[str, ...] | list[str] | None = None,
    assignee: str | None = None,
    reporter: str | None = None,
    status: tuple[str, ...] | list[str] | None = None,
    issue_type: tuple[str, ...] | list[str] | None = None,
    priority: tuple[str, ...] | list[str] | None = None,
    labels: tuple[str, ...] | list[str] | None = None,
    fix_version: tuple[str, ...] | list[str] | None = None,
    parent: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    updated_after: str | None = None,
    updated_before: str | None = None,
    text: str | None = None,
    exclude_closed: bool = True,
    order_by: str | None = "updated DESC",
) -> str:
    """Build a JQL query string from individual filter parameters.
    
    Args:
        project: Project key
        component: Component names (multiple values = OR)
        assignee: Assignee (use 'me' for current user, 'unassigned' for empty)
        reporter: Reporter (use 'me' for current user)
        status: Status values (multiple values = OR)
        issue_type: Issue types (multiple values = OR)
        priority: Priority levels (multiple values = OR)
        labels: Labels (multiple values = AND - issue must have all labels)
        fix_version: Fix versions (multiple values = OR)
        parent: Parent issue key (for epics or subtask parents)
        created_after: Issues created after this date
        created_before: Issues created before this date
        updated_after: Issues updated after this date
        updated_before: Issues updated before this date
        text: Full-text search across summary, description, comments
        exclude_closed: If True, exclude Done/Discarded status (default True)
        order_by: Sort order for results
    
    Returns:
        JQL query string
    """
    clauses = []
    
    # Project filter
    if project:
        clauses.append(f'project = "{project}"')
    
    # Component filter (OR between multiple values)
    if component:
        if len(component) == 1:
            clauses.append(f'component = "{component[0]}"')
        else:
            components_jql = " OR ".join(f'component = "{c}"' for c in component)
            clauses.append(f"({components_jql})")
    
    # Assignee filter
    if assignee:
        if assignee.lower() == "me":
            clauses.append("assignee = currentUser()")
        elif assignee.lower() == "unassigned":
            clauses.append("assignee IS EMPTY")
        else:
            clauses.append(f'assignee = "{assignee}"')
    
    # Reporter filter
    if reporter:
        if reporter.lower() == "me":
            clauses.append("reporter = currentUser()")
        else:
            clauses.append(f'reporter = "{reporter}"')
    
    # Status filter (OR between multiple values)
    if status:
        if len(status) == 1:
            clauses.append(f'status = "{status[0]}"')
        else:
            status_jql = " OR ".join(f'status = "{s}"' for s in status)
            clauses.append(f"({status_jql})")
    
    # Issue type filter (OR between multiple values)
    if issue_type:
        if len(issue_type) == 1:
            clauses.append(f'issuetype = "{issue_type[0]}"')
        else:
            types_jql = " OR ".join(f'issuetype = "{t}"' for t in issue_type)
            clauses.append(f"({types_jql})")
    
    # Priority filter (OR between multiple values)
    if priority:
        if len(priority) == 1:
            clauses.append(f'priority = "{priority[0]}"')
        else:
            priority_jql = " OR ".join(f'priority = "{p}"' for p in priority)
            clauses.append(f"({priority_jql})")
    
    # Labels filter (AND - issue must have all labels)
    if labels:
        for label in labels:
            clauses.append(f'labels = "{label}"')
    
    # Fix version filter (OR between multiple values)
    if fix_version:
        if len(fix_version) == 1:
            clauses.append(f'fixVersion = "{fix_version[0]}"')
        else:
            fv_jql = " OR ".join(f'fixVersion = "{fv}"' for fv in fix_version)
            clauses.append(f"({fv_jql})")
    
    # Parent filter (epic or parent issue)
    if parent:
        clauses.append(f'parent = "{parent}"')
    
    # Date filters
    if created_after:
        clauses.append(f"created >= {created_after}")
    if created_before:
        clauses.append(f"created <= {created_before}")
    if updated_after:
        clauses.append(f"updated >= {updated_after}")
    if updated_before:
        clauses.append(f"updated <= {updated_before}")
    
    # Text search
    if text:
        clauses.append(f'text ~ "{text}"')
    
    # Exclude closed issues by default
    if exclude_closed:
        clauses.append('status NOT IN ("Done", "Discarded")')
    
    # Build final query
    jql = " AND ".join(clauses)
    
    # Add ORDER BY if specified
    if order_by:
        jql += f" ORDER BY {order_by}"
    
    return jql


# =============================================================================
# Command Group
# =============================================================================


@click.group("issue")
def issue():
    """Work with JIRA issues."""
    pass


# =============================================================================
# Import and register subcommands
# =============================================================================

# Import commands after defining the group to avoid circular imports
from jira_tool.commands.issue.get import issue_get
from jira_tool.commands.issue.search import issue_search
from jira_tool.commands.issue.children import issue_children
from jira_tool.commands.issue.create import issue_create
from jira_tool.commands.issue.edit import issue_edit

# Commands are registered via decorators in their respective modules
