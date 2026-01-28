"""Issue-related CLI commands."""

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
from jira_tool.utils import filter_custom_fields, simplify_issue


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


def handle_api_errors(func):
    """Decorator to catch and display API errors cleanly."""
    @wraps(func)
    def wrapper(ctx, *args, **kwargs):
        try:
            return func(ctx, *args, **kwargs)
        except JiraError as e:
            click.echo(click.style(e.format_error(), fg="red"), err=True)
            
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


# Import pass_context from cli module (will be set up during registration)
# This is a forward reference that will be resolved when the module is used
pass_context = None


def set_pass_context(ctx_decorator):
    """Set the pass_context decorator from the main CLI module."""
    global pass_context
    pass_context = ctx_decorator


def build_jql_query(
    project: str | None = None,
    component: tuple[str, ...] | None = None,
    assignee: str | None = None,
    reporter: str | None = None,
    status: tuple[str, ...] | None = None,
    issue_type: tuple[str, ...] | None = None,
    priority: tuple[str, ...] | None = None,
    labels: tuple[str, ...] | None = None,
    fix_version: tuple[str, ...] | None = None,
    parent: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    updated_after: str | None = None,
    updated_before: str | None = None,
    text: str | None = None,
    unresolved: bool = False,
    exclude_closed: bool = True,
    order_by: str | None = None,
) -> str:
    """Build a JQL query from individual filter parameters."""
    clauses = []
    
    # Project
    if project:
        clauses.append(f'project = "{project}"')
    
    # Component (IN operator for multiple)
    if component:
        if len(component) == 1:
            clauses.append(f'component = "{component[0]}"')
        else:
            quoted = ', '.join(f'"{c}"' for c in component)
            clauses.append(f'component IN ({quoted})')
    
    # Assignee
    if assignee:
        if assignee.lower() == "me":
            clauses.append("assignee = currentUser()")
        elif assignee.lower() == "unassigned":
            clauses.append("assignee IS EMPTY")
        else:
            clauses.append(f'assignee = "{assignee}"')
    
    # Reporter
    if reporter:
        if reporter.lower() == "me":
            clauses.append("reporter = currentUser()")
        else:
            clauses.append(f'reporter = "{reporter}"')
    
    # Status (IN operator for multiple)
    if status:
        if len(status) == 1:
            clauses.append(f'status = "{status[0]}"')
        else:
            quoted = ', '.join(f'"{s}"' for s in status)
            clauses.append(f'status IN ({quoted})')
    elif exclude_closed:
        # Exclude closed statuses by default when no explicit status filter
        clauses.append('status NOT IN ("Done", "Discarded", "Closed", "Resolved")')
    
    # Issue Type (IN operator for multiple)
    if issue_type:
        if len(issue_type) == 1:
            clauses.append(f'issuetype = "{issue_type[0]}"')
        else:
            quoted = ', '.join(f'"{t}"' for t in issue_type)
            clauses.append(f'issuetype IN ({quoted})')
    
    # Priority (IN operator for multiple)
    if priority:
        if len(priority) == 1:
            clauses.append(f'priority = "{priority[0]}"')
        else:
            quoted = ', '.join(f'"{p}"' for p in priority)
            clauses.append(f'priority IN ({quoted})')
    
    # Labels (IN operator for multiple)
    if labels:
        if len(labels) == 1:
            clauses.append(f'labels = "{labels[0]}"')
        else:
            quoted = ', '.join(f'"{l}"' for l in labels)
            clauses.append(f'labels IN ({quoted})')
    
    # Fix Version (IN operator for multiple)
    if fix_version:
        if len(fix_version) == 1:
            clauses.append(f'fixVersion = "{fix_version[0]}"')
        else:
            quoted = ', '.join(f'"{v}"' for v in fix_version)
            clauses.append(f'fixVersion IN ({quoted})')
    
    # Parent (for epic children or subtasks)
    if parent:
        clauses.append(f'parent = "{parent}"')
    
    # Date filters
    if created_after:
        clauses.append(f'created >= "{created_after}"')
    if created_before:
        clauses.append(f'created <= "{created_before}"')
    if updated_after:
        clauses.append(f'updated >= "{updated_after}"')
    if updated_before:
        clauses.append(f'updated <= "{updated_before}"')
    
    # Text search
    if text:
        clauses.append(f'text ~ "{text}"')
    
    # Unresolved only
    if unresolved:
        clauses.append("resolution IS EMPTY")
    
    # Build final query
    if not clauses:
        raise click.UsageError("At least one search filter is required")
    
    jql = " AND ".join(clauses)
    
    # Order by
    if order_by:
        jql += f" ORDER BY {order_by}"
    
    return jql


@click.group()
def issue():
    """Commands for working with JIRA issues."""
    pass


@issue.command("get")
@click.argument("issue_key")
@click.option(
    "--raw", is_flag=True, default=False,
    help="Output raw API response instead of simplified view"
)
@click.option(
    "--include-custom-fields", is_flag=True, default=False,
    help="Include customfield_* fields in raw output (only applies with --raw)"
)
@click.option(
    "--comments", is_flag=True, default=False,
    help="Include comments in the output"
)
@format_options
@click.pass_obj
@handle_api_errors
def issue_get(ctx, issue_key: str, raw: bool, include_custom_fields: bool, comments: bool, output_format: str):
    """Get details of a specific issue."""
    issue = ctx.client.get_issue(issue_key)
    
    # Fetch comments if requested
    issue_comments = None
    if comments:
        issue_comments = ctx.client.get_issue_comments(issue_key)
    
    # Fetch children (issues with this as parent)
    children_result = ctx.client.search_issues(f"parent = {issue_key}", max_results=100)
    children_issues = children_result.get("issues", [])
    
    if raw:
        if not include_custom_fields:
            issue = filter_custom_fields(issue)
        if issue_comments is not None:
            issue["comments"] = issue_comments
        if children_issues:
            issue["children"] = children_issues
        output_data(issue, output_format)
    else:
        simplified = simplify_issue(issue, comments=issue_comments, children=children_issues)
        output_data(simplified, output_format)


@issue.command("search")
@click.option("--jql", default=None, help="Raw JQL query string (overrides other filters)")
@click.option("--project", "-p", default=None, help="Project key (e.g., AIGENPI)")
@click.option("--component", "-c", multiple=True, help="Component name (can specify multiple)")
@click.option("--assignee", "-a", default=None, help="Assignee email/name (use 'me' for yourself, 'unassigned' for none)")
@click.option("--reporter", default=None, help="Reporter email/name (use 'me' for yourself)")
@click.option("--status", "-s", multiple=True, help="Status (e.g., Open, 'In Progress', Done)")
@click.option("--type", "issue_type", multiple=True, help="Issue type (e.g., Story, Bug, Epic, Task)")
@click.option("--priority", multiple=True, help="Priority (e.g., 'P1: High', 'P2: Medium')")
@click.option("--label", "labels", multiple=True, help="Label (can specify multiple)")
@click.option("--fix-version", multiple=True, help="Fix version (can specify multiple)")
@click.option("--parent", default=None, help="Parent issue key (for epic children or subtasks)")
@click.option("--created-after", default=None, help="Created after date (YYYY-MM-DD or -7d for relative)")
@click.option("--created-before", default=None, help="Created before date (YYYY-MM-DD)")
@click.option("--updated-after", default=None, help="Updated after date (YYYY-MM-DD or -7d for relative)")
@click.option("--updated-before", default=None, help="Updated before date (YYYY-MM-DD)")
@click.option("--text", "-q", "search_text", default=None, help="Full-text search across summary, description, comments")
@click.option("--unresolved", "-u", is_flag=True, default=False, help="Only show unresolved issues")
@click.option("--allow-closed", is_flag=True, default=False, help="Include Done/Discarded issues (excluded by default)")
@click.option("--order-by", default="updated DESC", help="Sort order (default: 'updated DESC')")
@click.option("--limit", default=50, help="Maximum results to return")
@click.option("--show-jql", is_flag=True, default=False, help="Print the generated JQL query")
@format_options
@click.pass_obj
@handle_api_errors
def issue_search(
    ctx,
    jql: str | None,
    project: str | None,
    component: tuple[str, ...],
    assignee: str | None,
    reporter: str | None,
    status: tuple[str, ...],
    issue_type: tuple[str, ...],
    priority: tuple[str, ...],
    labels: tuple[str, ...],
    fix_version: tuple[str, ...],
    parent: str | None,
    created_after: str | None,
    created_before: str | None,
    updated_after: str | None,
    updated_before: str | None,
    search_text: str | None,
    unresolved: bool,
    allow_closed: bool,
    order_by: str | None,
    limit: int,
    show_jql: bool,
    output_format: str,
):
    """Search for issues using filters or JQL.
    
    \b
    Examples:
      # Find my open issues in a project
      jira-tool issue search -p AIGENPI -a me -u
      
      # Find issues by component
      jira-tool issue search --component rocWMMA --component hipBLASLt
      
      # Find recently updated bugs
      jira-tool issue search --type Bug --updated-after -7d
      
      # Text search
      jira-tool issue search --text "memory leak" -p AIGENPI
      
      # Raw JQL (overrides all other filters)
      jira-tool issue search --jql "project = AIGENPI AND status = Open"
    """
    # Build JQL from filters if not provided directly
    if jql is None:
        # Check if any filters were provided
        has_filters = any([
            project, component, assignee, reporter, status, issue_type,
            priority, labels, fix_version, parent, created_after, created_before,
            updated_after, updated_before, search_text, unresolved
        ])
        if not has_filters:
            raise click.UsageError(
                "Provide either --jql or at least one filter option.\n"
                "See 'jira-tool issue search --help' for available filters."
            )
        
        jql = build_jql_query(
            project=project,
            component=component if component else None,
            assignee=assignee,
            reporter=reporter,
            status=status if status else None,
            issue_type=issue_type if issue_type else None,
            priority=priority if priority else None,
            labels=labels if labels else None,
            fix_version=fix_version if fix_version else None,
            parent=parent,
            created_after=created_after,
            created_before=created_before,
            updated_after=updated_after,
            updated_before=updated_before,
            text=search_text,
            unresolved=unresolved,
            exclude_closed=not allow_closed,
            order_by=order_by,
        )
    
    if show_jql:
        click.echo(click.style(f"JQL: {jql}", fg="cyan"), err=True)
        click.echo("", err=True)
    
    result = ctx.client.search_issues(jql, max_results=limit)
    issues = result.get("issues", [])
    
    if output_format == "text":
        if not issues:
            click.echo("No issues found.")
        else:
            format_issues_compact(issues)
    elif output_format == "list":
        for issue in issues:
            click.echo(issue.get("key", ""))
    elif output_format == "csv":
        simplified = [simplify_issue(issue) for issue in issues]
        click.echo(format_issues_csv(simplified), nl=False)
    else:
        simplified = [simplify_issue(issue) for issue in issues]
        output_data(simplified, output_format)


@issue.command("children")
@click.argument("issue_key")
@click.option("--limit", default=50, help="Maximum results to return")
@format_options
@click.pass_obj
@handle_api_errors
def issue_children(ctx, issue_key: str, limit: int, output_format: str):
    """Get child issues of an epic or parent issue."""
    result = ctx.client.search_issues(f"parent = {issue_key}", max_results=limit)
    issues = result.get("issues", [])
    
    if output_format == "text":
        if not issues:
            click.echo(f"No child issues found for {issue_key}")
        else:
            format_issues_compact(issues)
    elif output_format == "list":
        for issue in issues:
            click.echo(issue.get("key", ""))
    elif output_format == "csv":
        simplified = [simplify_issue(issue) for issue in issues]
        click.echo(format_issues_csv(simplified), nl=False)
    else:
        simplified = [simplify_issue(issue) for issue in issues]
        output_data(simplified, output_format)
