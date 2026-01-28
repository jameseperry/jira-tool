"""Command-line interface for JIRA tool."""

import csv
import io
import json
import sys
from functools import wraps
from typing import Any

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from jira_tool.client import JiraClient, JiraError


def normalize_priority(priority: str | None) -> str | None:
    """Normalize priority to short form (P1, P2, P3, etc.)."""
    if not priority:
        return None
    # Extract Pn prefix if present (e.g., "P1: High" -> "P1")
    if priority.startswith("P") and len(priority) >= 2 and priority[1].isdigit():
        return priority.split(":")[0].split()[0]  # Get just "Pn" part
    return priority


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


def output_data(data: Any, fmt: str) -> None:
    """Output data in the specified format."""
    if fmt == "json":
        click.echo(json.dumps(data, indent=2))
    elif fmt == "yaml":
        click.echo(yaml.dump(data, default_flow_style=False, sort_keys=False))
    elif fmt == "text":
        # format_issue_text prints directly via Rich, returns empty string
        result = format_issue_text(data)
        if result:
            click.echo(result)


def format_issues_csv(issues: list[dict]) -> str:
    """Format a list of simplified issues as CSV."""
    if not issues:
        return ""
    
    # Define columns for CSV output
    columns = [
        ("key", "Key"),
        ("summary", "Summary"),
        ("status", "Status"),
        ("type", "Type"),
        ("priority", "Priority"),
        ("assignee", "Assignee"),
        ("reporter", "Reporter"),
        ("created", "Created"),
        ("updated", "Updated"),
        ("due_date", "Due Date"),
        ("components", "Components"),
        ("labels", "Labels"),
        ("fix_versions", "Fix Versions"),
        ("parent_key", "Parent"),
    ]
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([col[1] for col in columns])
    
    # Write data rows
    for issue in issues:
        row = []
        for field_name, _ in columns:
            if field_name == "parent_key":
                parent = issue.get("parent")
                value = parent.get("key") if parent else ""
            elif field_name in ("components", "labels", "fix_versions"):
                # Join lists with semicolons
                value = ";".join(issue.get(field_name, []) or [])
            elif field_name in ("created", "updated"):
                # Just the date part
                full_date = issue.get(field_name, "")
                value = full_date[:10] if full_date else ""
            else:
                value = issue.get(field_name, "") or ""
            row.append(value)
        writer.writerow(row)
    
    return output.getvalue()


def format_issues_compact(issues: list[dict]) -> None:
    """Format issues as a rich table."""
    console = Console()
    
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Key", style="bold cyan", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("Priority", no_wrap=True)
    table.add_column("Assignee", no_wrap=True)
    table.add_column("Components", no_wrap=True, ratio=1)
    table.add_column("Summary", ratio=3)
    
    for issue in issues:
        fields = issue.get("fields", {})
        key = issue.get("key", "?")
        summary = (fields.get("summary") or "").strip()
        status = fields.get("status", {}).get("name", "?")
        issue_type = fields.get("issuetype", {}).get("name", "?")
        priority_raw = fields.get("priority", {}).get("name") if fields.get("priority") else None
        priority = normalize_priority(priority_raw) or "-"
        assignee = fields.get("assignee", {}).get("displayName", "-") if fields.get("assignee") else "-"
        components = [c.get("name", "") for c in fields.get("components", [])]
        components_str = ", ".join(components) if components else "-"
        
        # Truncate summary if too long
        max_summary = 60
        if len(summary) > max_summary:
            summary = summary[:max_summary - 3] + "..."
        
        # Truncate assignee name
        if len(assignee) > 18:
            assignee = assignee[:15] + "..."
        
        # Truncate components if too long
        if len(components_str) > 30:
            components_str = components_str[:27] + "..."
        
        # Color-code status
        status_colors = {
            "Done": "green",
            "Closed": "green",
            "Resolved": "green",
            "Discarded": "dim",
            "In Progress": "yellow",
            "Implementation": "yellow",
            "Review": "cyan",
            "In Review": "cyan",
            "Open": "white",
        }
        status_text = Text(status, style=status_colors.get(status, "white"))
        
        # Color-code priority
        priority_colors = {
            "P1": "red bold",
            "P2": "yellow",
            "P3": "dim",
        }
        priority_text = Text(priority, style=priority_colors.get(priority, "white"))
        
        # Color-code issue type
        type_colors = {
            "Bug": "red",
            "Epic": "magenta bold",
            "Story": "green",
            "Task": "blue",
            "Sub-task": "dim blue",
        }
        type_text = Text(issue_type, style=type_colors.get(issue_type, "white"))
        
        # Use Text() for summary to prevent Rich from interpreting [brackets] as markup
        table.add_row(key, status_text, type_text, priority_text, assignee, components_str, Text(summary))
    
    console.print(table)


def format_issue_text(issue: dict) -> str:
    """Format a simplified issue as human-readable text using Rich."""
    console = Console()
    
    # Color mappings
    status_colors = {
        "Done": "green", "Closed": "green", "Resolved": "green",
        "Discarded": "dim",
        "In Progress": "yellow", "Implementation": "yellow",
        "Review": "cyan", "In Review": "cyan",
        "Open": "white",
    }
    priority_colors = {"P1": "red bold", "P2": "yellow", "P3": "dim"}
    type_colors = {
        "Bug": "red", "Epic": "magenta bold", "Story": "green",
        "Task": "blue", "Sub-task": "dim blue",
    }
    
    # Build the content
    lines = []
    
    # Summary as first line
    summary = (issue.get("summary") or "").strip()
    # Escape brackets to prevent Rich interpreting them as markup
    summary_escaped = summary.replace("[", "\\[").replace("]", "\\]")
    lines.append(f"[bold]{summary_escaped}[/bold]")
    lines.append("")
    
    # Status/Type/Priority line with colors
    meta_parts = []
    if issue.get("status"):
        status = issue["status"]
        color = status_colors.get(status, "white")
        meta_parts.append(f"[{color}]{status}[/{color}]")
    if issue.get("type"):
        issue_type = issue["type"]
        color = type_colors.get(issue_type, "white")
        meta_parts.append(f"[{color}]{issue_type}[/{color}]")
    if issue.get("priority"):
        priority = issue["priority"]
        color = priority_colors.get(priority, "white")
        meta_parts.append(f"[{color}]{priority}[/{color}]")
    if meta_parts:
        lines.append(" • ".join(meta_parts))
    
    # People
    if issue.get("assignee"):
        lines.append(f"[bold]Assignee:[/bold] {issue['assignee']}")
    if issue.get("reporter"):
        lines.append(f"[bold]Reporter:[/bold] {issue['reporter']}")
    
    # Project
    if issue.get("project"):
        lines.append(f"[bold]Project:[/bold] {issue['project']['name']} ({issue['project']['key']})")
    
    # Parent/Epic
    if issue.get("parent"):
        lines.append(f"[bold]Parent:[/bold] [cyan]{issue['parent']['key']}[/cyan] - {issue['parent']['summary']}")
    
    # Dates
    if issue.get("created"):
        lines.append(f"[bold]Created:[/bold] {issue['created'][:10]}")
    if issue.get("updated"):
        lines.append(f"[bold]Updated:[/bold] {issue['updated'][:10]}")
    if issue.get("due_date"):
        lines.append(f"[bold]Due:[/bold] {issue['due_date']}")
    
    # Time tracking
    if issue.get("time_tracking"):
        tt = issue["time_tracking"]
        tt_parts = []
        if tt.get("original_estimate"):
            tt_parts.append(f"[bold]Estimate:[/bold] {tt['original_estimate']}")
        if tt.get("time_spent"):
            tt_parts.append(f"[bold]Spent:[/bold] {tt['time_spent']}")
        if tt.get("remaining_estimate"):
            tt_parts.append(f"[bold]Remaining:[/bold] {tt['remaining_estimate']}")
        if tt_parts:
            lines.append("  ".join(tt_parts))
    
    # Labels & Components
    if issue.get("labels"):
        lines.append(f"[bold]Labels:[/bold] {', '.join(issue['labels'])}")
    if issue.get("components"):
        lines.append(f"[bold]Components:[/bold] {', '.join(issue['components'])}")
    if issue.get("fix_versions"):
        lines.append(f"[bold]Fix Versions:[/bold] {', '.join(issue['fix_versions'])}")
    
    # Description
    if issue.get("description"):
        lines.append("")
        lines.append("[bold]Description:[/bold]")
        # Escape any Rich markup in description
        for desc_line in issue["description"].split("\n"):
            # Escape brackets to prevent Rich interpreting them as markup
            escaped = desc_line.replace("[", "\\[").replace("]", "\\]")
            lines.append(f"  {escaped}")
    
    # Subtasks
    if issue.get("subtasks"):
        lines.append("")
        lines.append("[bold]Subtasks:[/bold]")
        for st in issue["subtasks"]:
            if st["status"] in ("Done", "Closed", "Resolved"):
                indicator = "[green]✓[/green]"
            else:
                indicator = "○"
            lines.append(f"  {indicator} [cyan]{st['key']}[/cyan]: {st['summary']} [{st['status']}]")
    
    # Links
    if issue.get("links"):
        lines.append("")
        lines.append("[bold]Links:[/bold]")
        for link in issue["links"]:
            lines.append(f"  {link['type']} ({link['direction']}): [cyan]{link['key']}[/cyan] - {link['summary']}")
    
    # Children (epic children, etc.)
    if issue.get("children"):
        lines.append("")
        lines.append("[bold]Children:[/bold]")
        for child in issue["children"]:
            status = child.get("status", "?")
            if status in ("Done", "Closed", "Resolved"):
                indicator = "[green]✓[/green]"
            else:
                indicator = "○"
            child_type = child.get("type", "")
            lines.append(f"  {indicator} [cyan]{child['key']}[/cyan]: {child['summary']} [{child_type}] [{status}]")
    
    # Comments
    if issue.get("comments"):
        lines.append("")
        lines.append("[bold]Comments:[/bold]")
        for comment in issue["comments"]:
            author = comment.get("author", "Unknown")
            created = comment.get("created", "")[:10] if comment.get("created") else ""
            lines.append("")
            lines.append(f"  [bold]{author}[/bold] [dim]({created})[/dim]")
            body = comment.get("body", "")
            if body:
                for body_line in body.split("\n"):
                    # Escape brackets in comment body
                    escaped = body_line.replace("[", "\\[").replace("]", "\\]")
                    lines.append(f"    {escaped}")
    
    content = "\n".join(lines)
    
    # Create panel with issue key as title
    panel = Panel(content, title=f"[bold cyan]{issue['key']}[/bold cyan]", title_align="left", border_style="dim")
    
    # Print directly to console and return empty string
    # (since output_data expects a string but we're using Rich)
    console.print(panel)
    return ""


def filter_custom_fields(data: dict) -> dict:
    """Recursively remove customfield_* keys from a dictionary."""
    if not isinstance(data, dict):
        return data
    
    result = {}
    for key, value in data.items():
        if key.startswith("customfield_"):
            continue
        if isinstance(value, dict):
            result[key] = filter_custom_fields(value)
        elif isinstance(value, list):
            result[key] = [
                filter_custom_fields(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def extract_text_from_adf(adf: dict | None) -> str | None:
    """Extract plain text from Atlassian Document Format."""
    if not adf or not isinstance(adf, dict):
        return None
    
    def extract_content(node: dict) -> str:
        if node.get("type") == "text":
            return node.get("text", "")
        
        content = node.get("content", [])
        parts = []
        for child in content:
            if isinstance(child, dict):
                parts.append(extract_content(child))
        
        # Add newlines for block elements
        if node.get("type") in ("paragraph", "heading", "listItem", "tableCell"):
            return "".join(parts) + "\n"
        elif node.get("type") == "hardBreak":
            return "\n"
        
        return "".join(parts)
    
    return extract_content(adf).strip() or None


def simplify_issue(issue: dict, comments: list[dict] | None = None, children: list[dict] | None = None) -> dict:
    """Convert raw JIRA API issue to a simplified format."""
    fields = issue.get("fields", {})
    
    simplified = {
        "key": issue.get("key"),
        "id": issue.get("id"),
        "summary": (fields.get("summary") or "").strip(),
        "description": extract_text_from_adf(fields.get("description")),
        "status": fields.get("status", {}).get("name"),
        "type": fields.get("issuetype", {}).get("name"),
        "priority": normalize_priority(fields.get("priority", {}).get("name")),
        "resolution": fields.get("resolution", {}).get("name") if fields.get("resolution") else None,
        "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
        "reporter": fields.get("reporter", {}).get("displayName") if fields.get("reporter") else None,
        "created": fields.get("created"),
        "updated": fields.get("updated"),
        "due_date": fields.get("duedate"),
        "labels": fields.get("labels", []),
        "components": [c.get("name") for c in fields.get("components", [])],
        "fix_versions": [v.get("name") for v in fields.get("fixVersions", [])],
        "project": {
            "key": fields.get("project", {}).get("key"),
            "name": fields.get("project", {}).get("name"),
        },
    }
    
    # Add parent/epic link if present
    parent = fields.get("parent")
    if parent:
        simplified["parent"] = {
            "key": parent.get("key"),
            "summary": parent.get("fields", {}).get("summary"),
        }
    
    # Add time tracking if present
    time_tracking = fields.get("timetracking", {})
    if time_tracking:
        simplified["time_tracking"] = {
            "original_estimate": time_tracking.get("originalEstimate"),
            "remaining_estimate": time_tracking.get("remainingEstimate"),
            "time_spent": time_tracking.get("timeSpent"),
        }
    
    # Add subtasks if present
    subtasks = fields.get("subtasks", [])
    if subtasks:
        simplified["subtasks"] = [
            {
                "key": st.get("key"),
                "summary": st.get("fields", {}).get("summary"),
                "status": st.get("fields", {}).get("status", {}).get("name"),
            }
            for st in subtasks
        ]
    
    # Add links if present
    links = fields.get("issuelinks", [])
    if links:
        simplified["links"] = []
        for link in links:
            link_type = link.get("type", {}).get("name")
            if "outwardIssue" in link:
                simplified["links"].append({
                    "type": link_type,
                    "direction": "outward",
                    "key": link["outwardIssue"].get("key"),
                    "summary": link["outwardIssue"].get("fields", {}).get("summary"),
                })
            if "inwardIssue" in link:
                simplified["links"].append({
                    "type": link_type,
                    "direction": "inward",
                    "key": link["inwardIssue"].get("key"),
                    "summary": link["inwardIssue"].get("fields", {}).get("summary"),
                })
    
    # Add children if provided
    if children:
        simplified["children"] = [
            {
                "key": c.get("key"),
                "summary": c.get("fields", {}).get("summary"),
                "status": c.get("fields", {}).get("status", {}).get("name"),
                "type": c.get("fields", {}).get("issuetype", {}).get("name"),
            }
            for c in children
        ]
    
    # Add comments if provided
    if comments:
        simplified["comments"] = [
            {
                "author": c.get("author", {}).get("displayName", "Unknown"),
                "created": c.get("created"),
                "body": extract_text_from_adf(c.get("body")),
            }
            for c in comments
        ]
    
    return simplified


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


class Context:
    def __init__(self):
        self.client: JiraClient | None = None
        self.debug: bool = False


# Use ensure=False so it doesn't create a new Context if one isn't found
# (which would indicate a bug in our command structure)
pass_context = click.make_pass_decorator(Context)


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


# =============================================================================
# Issue commands
# =============================================================================
@cli.group()
def issue():
    """Commands for working with JIRA issues."""
    pass


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
@pass_context
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
@pass_context
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
@pass_context
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


# =============================================================================
# Project commands
# =============================================================================
@cli.group()
def project():
    """Commands for working with JIRA projects."""
    pass


@project.command("list")
@pass_context
def project_list(ctx):
    """List all accessible projects."""
    # TODO: Implement
    click.echo("Listing projects...")


# =============================================================================
# Add more command groups here as needed
# =============================================================================
