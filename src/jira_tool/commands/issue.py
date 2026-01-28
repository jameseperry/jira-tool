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
from jira_tool.utils import (
    filter_custom_fields,
    simplify_issue,
    filter_fields,
    parse_fields_option,
    AVAILABLE_FIELDS,
    DEFAULT_FIELDS_GET,
    DEFAULT_FIELDS_SEARCH,
)


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
@click.argument("issue_keys", nargs=-1, required=True)
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
@click.option(
    "--fields", "-f", default=None,
    help="Comma-separated list of fields to include. Use +field to add, -field to remove from defaults. Use 'all' for all fields."
)
@format_options
@click.pass_obj
@handle_api_errors
def issue_get(ctx, issue_keys: tuple[str, ...], raw: bool, include_custom_fields: bool, comments: bool, fields: str | None, output_format: str):
    """Get details of one or more issues.
    
    You can provide multiple issue keys to fetch them all at once.
    
    \b
    Field selection examples:
      --fields key,summary,status      # Only these fields
      --fields +labels,+description    # Add to defaults
      --fields -components,-created    # Remove from defaults
      --fields all                     # All available fields
    """
    results = []
    selected_fields = parse_fields_option(fields, DEFAULT_FIELDS_GET)
    
    # If comments requested, ensure comments field is included
    if comments:
        selected_fields.add("comments")
    
    for issue_key in issue_keys:
        issue = ctx.client.get_issue(issue_key)
        
        # Fetch comments if requested or if comments field is selected
        issue_comments = None
        if comments or "comments" in selected_fields:
            issue_comments = ctx.client.get_issue_comments(issue_key)
        
        # Fetch children (issues with this as parent) if children field is selected
        children_issues = []
        if "children" in selected_fields:
            children_result = ctx.client.search_issues(f"parent = {issue_key}", max_results=100)
            children_issues = children_result.get("issues", [])
        
        if raw:
            if not include_custom_fields:
                issue = filter_custom_fields(issue)
            if issue_comments is not None:
                issue["comments"] = issue_comments
            if children_issues:
                issue["children"] = children_issues
            results.append(issue)
        else:
            simplified = simplify_issue(issue, comments=issue_comments, children=children_issues)
            # Apply field filtering
            filtered = filter_fields(simplified, selected_fields)
            results.append(filtered)
    
    # Output results
    if len(results) == 1:
        output_data(results[0], output_format)
    else:
        # For multiple issues, output as list for JSON/YAML, or one-by-one for text
        if output_format == "text":
            for result in results:
                output_data(result, output_format)
        else:
            output_data(results, output_format)


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
@click.option("--allow-closed", is_flag=True, default=False, help="Include Done/Discarded issues (excluded by default)")
@click.option("--order-by", default="updated DESC", help="Sort order (default: 'updated DESC')")
@click.option("--limit", default=50, help="Maximum results to return")
@click.option("--show-jql", is_flag=True, default=False, help="Print the generated JQL query")
@click.option(
    "--fields", "-f", default=None,
    help="Comma-separated list of fields to include. Use +field to add, -field to remove from defaults. Use 'all' for all fields."
)
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
    allow_closed: bool,
    order_by: str | None,
    limit: int,
    show_jql: bool,
    fields: str | None,
    output_format: str,
):
    """Search for issues using filters or JQL.
    
    \b
    Examples:
      # Find my open issues in a project
      jira-tool issue search -p PROJ -a me
      
      # Find issues by component
      jira-tool issue search -p PROJ --component Backend
      
      # Find recently updated bugs
      jira-tool issue search --type Bug --updated-after -7d
      
      # Text search
      jira-tool issue search --text "memory leak" -p PROJ
      
      # Raw JQL (overrides all other filters)
      jira-tool issue search --jql "project = PROJ AND status = Open"
    """
    # Build JQL from filters if not provided directly
    if jql is None:
        # Check if any filters were provided
        has_filters = any([
            project, component, assignee, reporter, status, issue_type,
            priority, labels, fix_version, parent, created_after, created_before,
            updated_after, updated_before, search_text
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
            exclude_closed=not allow_closed,
            order_by=order_by,
        )
    
    if show_jql:
        click.echo(click.style(f"JQL: {jql}", fg="cyan"), err=True)
        click.echo("", err=True)
    
    result = ctx.client.search_issues(jql, max_results=limit)
    issues = result.get("issues", [])
    selected_fields = parse_fields_option(fields, DEFAULT_FIELDS_SEARCH)
    
    if output_format == "text":
        if not issues:
            click.echo("No issues found.")
        else:
            format_issues_compact(issues, selected_fields)
    elif output_format == "list":
        for issue in issues:
            click.echo(issue.get("key", ""))
    elif output_format == "csv":
        simplified = [filter_fields(simplify_issue(issue), selected_fields) for issue in issues]
        click.echo(format_issues_csv(simplified), nl=False)
    else:
        simplified = [filter_fields(simplify_issue(issue), selected_fields) for issue in issues]
        output_data(simplified, output_format)


@issue.command("children")
@click.argument("issue_key")
@click.option("--limit", default=50, help="Maximum results to return")
@click.option(
    "--fields", "-f", default=None,
    help="Comma-separated list of fields to include. Use +field to add, -field to remove from defaults. Use 'all' for all fields."
)
@format_options
@click.pass_obj
@handle_api_errors
def issue_children(ctx, issue_key: str, limit: int, fields: str | None, output_format: str):
    """Get child issues of an epic or parent issue."""
    result = ctx.client.search_issues(f"parent = {issue_key}", max_results=limit)
    issues = result.get("issues", [])
    selected_fields = parse_fields_option(fields, DEFAULT_FIELDS_SEARCH)
    
    if output_format == "text":
        if not issues:
            click.echo(f"No child issues found for {issue_key}")
        else:
            format_issues_compact(issues, selected_fields)
    elif output_format == "list":
        for issue in issues:
            click.echo(issue.get("key", ""))
    elif output_format == "csv":
        simplified = [filter_fields(simplify_issue(issue), selected_fields) for issue in issues]
        click.echo(format_issues_csv(simplified), nl=False)
    else:
        simplified = [filter_fields(simplify_issue(issue), selected_fields) for issue in issues]
        output_data(simplified, output_format)


@issue.command("create")
@click.option("--project", "-p", required=True, help="Project key (e.g., PROJ)")
@click.option("--summary", "-s", required=True, help="Issue summary/title")
@click.option("--type", "issue_type", default="Task", help="Issue type (default: Task)")
@click.option("--description", "-d", default=None, help="Issue description")
@click.option("--assignee", "-a", default=None, help="Assignee account ID or email")
@click.option("--priority", default=None, help="Priority name (e.g., 'P1: High')")
@click.option("--label", "labels", multiple=True, help="Label (can specify multiple)")
@click.option("--component", "components", multiple=True, help="Component name (can specify multiple)")
@click.option("--parent", default=None, help="Parent issue key (for sub-tasks or epic children)")
@click.option("--field", "extra_fields", multiple=True, help="Additional field in 'name=value' format. Field names are auto-translated to IDs.")
@click.option("--dry-run", is_flag=True, default=False, help="Show what would be created without actually creating it")
@format_options
@click.pass_obj
@handle_api_errors
def issue_create(
    ctx,
    project: str,
    summary: str,
    issue_type: str,
    description: str | None,
    assignee: str | None,
    priority: str | None,
    labels: tuple[str, ...],
    components: tuple[str, ...],
    parent: str | None,
    extra_fields: tuple[str, ...],
    dry_run: bool,
    output_format: str,
):
    """Create a new JIRA issue.
    
    \b
    Examples:
      # Create a simple task
      jira-tool issue create -p PROJ -s "Fix login bug"
      
      # Create a bug with description
      jira-tool issue create -p PROJ -s "Login fails" --type Bug -d "Users cannot log in"
      
      # Create issue with labels and components
      jira-tool issue create -p PROJ -s "New feature" --label backend --label api --component Backend
      
      # Create a sub-task under a parent
      jira-tool issue create -p PROJ -s "Sub-task" --type Sub-task --parent PROJ-123
      
      # Use custom fields by name (auto-translated to field IDs)
      jira-tool issue create -p PROJ -s "Bug" --type Bug \\
        --field "Severity=High" --field "Steps to Reproduce=1. Do X\\n2. Do Y"
      
      # Dry-run to see what would be created
      jira-tool issue create -p PROJ -s "Test" --dry-run
    """
    # Parse extra fields from "name=value" format
    parsed_extra_fields = {}
    for field_spec in extra_fields:
        if "=" not in field_spec:
            raise click.UsageError(f"Invalid field format: '{field_spec}'. Use 'name=value' format.")
        name, value = field_spec.split("=", 1)
        name = name.strip()
        value = value.strip()
        
        # Try to parse as JSON for complex values, otherwise use as string
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            # Handle escaped newlines in string values
            parsed_value = value.replace("\\n", "\n")
        
        parsed_extra_fields[name] = parsed_value
    
    # Translate field names to IDs if we have extra fields
    translated_extra_fields = None
    if parsed_extra_fields:
        translated_extra_fields = ctx.client.translate_field_names(parsed_extra_fields)
    # Build the payload preview
    payload = {
        "project": project,
        "summary": summary,
        "type": issue_type,
    }
    
    if description:
        payload["description"] = description
    if assignee:
        payload["assignee"] = assignee
    if priority:
        payload["priority"] = priority
    if labels:
        payload["labels"] = list(labels)
    if components:
        payload["components"] = list(components)
    if parent:
        payload["parent"] = parent
    if parsed_extra_fields:
        payload["extra_fields"] = parsed_extra_fields
        payload["extra_fields_translated"] = translated_extra_fields
    
    if dry_run:
        # Show what would be created
        click.echo(click.style("DRY RUN - No issue will be created", fg="yellow", bold=True), err=True)
        click.echo(click.style("─" * 50, fg="yellow"), err=True)
        click.echo("", err=True)
        
        click.echo(click.style("API Payload:", fg="cyan", bold=True), err=True)
        output_data(payload, output_format if output_format != "text" else "yaml")
        click.echo("", err=True)
        
        # Fake result for consistent output
        result = {
            "id": "00000",
            "key": f"{project}-XXXXX",
            "self": f"{ctx.client.base_url}/issue/00000",
        }
    else:
        # Actually create the issue
        result = ctx.client.create_issue(
            project_key=project,
            summary=summary,
            issue_type=issue_type,
            description=description,
            assignee=assignee,
            priority=priority,
            labels=list(labels) if labels else None,
            components=list(components) if components else None,
            parent=parent,
            extra_fields=translated_extra_fields,
        )
    
    # Extract key info from result
    issue_key = result.get("key", "")
    issue_id = result.get("id", "")
    issue_self = result.get("self", "")
    
    if output_format == "text":
        prefix = "[DRY RUN] " if dry_run else ""
        click.echo(click.style(f"✓ {prefix}Created issue: {issue_key}", fg="green", bold=True))
        
        # Build issue URL
        if ctx.client.base_url:
            browse_url = f"{ctx.client.base_url.replace('/rest/api/3', '')}/browse/{issue_key}"
            click.echo(f"  URL: {browse_url}")
    else:
        # Return simplified response for JSON/YAML
        output = {
            "key": issue_key,
            "id": issue_id,
            "self": issue_self,
            "created": True,
        }
        output_data(output, output_format)


@issue.command("edit")
@click.argument("issue_key")
@click.option("--summary", "-s", default=None, help="New issue summary/title")
@click.option("--description", "-d", default=None, help="New issue description")
@click.option("--assignee", "-a", default=None, help="New assignee (use '' to unassign)")
@click.option("--priority", default=None, help="New priority name")
@click.option("--label", "labels", multiple=True, help="Set labels (replaces existing, can specify multiple)")
@click.option("--component", "components", multiple=True, help="Set components (replaces existing, can specify multiple)")
@click.option("--field", "extra_fields", multiple=True, help="Additional field in 'name=value' format. Field names are auto-translated to IDs.")
@click.option("--dry-run", is_flag=True, default=False, help="Show what would be changed without actually updating")
@format_options
@click.pass_obj
@handle_api_errors
def issue_edit(
    ctx,
    issue_key: str,
    summary: str | None,
    description: str | None,
    assignee: str | None,
    priority: str | None,
    labels: tuple[str, ...],
    components: tuple[str, ...],
    extra_fields: tuple[str, ...],
    dry_run: bool,
    output_format: str,
):
    """Edit an existing JIRA issue.
    
    \b
    Examples:
      # Update summary
      jira-tool issue edit PROJ-123 -s "New title"
      
      # Update description
      jira-tool issue edit PROJ-123 -d "New description"
      
      # Change assignee
      jira-tool issue edit PROJ-123 -a user@example.com
      
      # Unassign issue
      jira-tool issue edit PROJ-123 -a ""
      
      # Update custom fields by name
      jira-tool issue edit PROJ-123 --field "Severity=Critical"
      
      # Multiple changes at once
      jira-tool issue edit PROJ-123 -s "New title" --priority "P1: High" --label urgent
      
      # Dry-run to see what would be changed
      jira-tool issue edit PROJ-123 -s "New title" --dry-run
    """
    # Check that at least one field is being changed
    has_changes = any([
        summary is not None,
        description is not None,
        assignee is not None,
        priority is not None,
        labels,
        components,
        extra_fields,
    ])
    
    if not has_changes:
        raise click.UsageError("No fields specified to update. Use --help to see available options.")
    
    # Parse extra fields from "name=value" format
    parsed_extra_fields = {}
    for field_spec in extra_fields:
        if "=" not in field_spec:
            raise click.UsageError(f"Invalid field format: '{field_spec}'. Use 'name=value' format.")
        name, value = field_spec.split("=", 1)
        name = name.strip()
        value = value.strip()
        
        # Try to parse as JSON for complex values, otherwise use as string
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            # Handle escaped newlines in string values
            parsed_value = value.replace("\\n", "\n")
        
        parsed_extra_fields[name] = parsed_value
    
    # Translate field names to IDs if we have extra fields
    translated_extra_fields = None
    if parsed_extra_fields:
        translated_extra_fields = ctx.client.translate_field_names(parsed_extra_fields)
    
    # Build the payload preview
    payload = {"issue": issue_key}
    
    if summary is not None:
        payload["summary"] = summary
    if description is not None:
        payload["description"] = description
    if assignee is not None:
        payload["assignee"] = assignee if assignee else "(unassign)"
    if priority is not None:
        payload["priority"] = priority
    if labels:
        payload["labels"] = list(labels)
    if components:
        payload["components"] = list(components)
    if parsed_extra_fields:
        payload["extra_fields"] = parsed_extra_fields
        payload["extra_fields_translated"] = translated_extra_fields
    
    if dry_run:
        # Show what would be changed
        click.echo(click.style("DRY RUN - No changes will be made", fg="yellow", bold=True), err=True)
        click.echo(click.style("─" * 50, fg="yellow"), err=True)
        click.echo("", err=True)
        
        click.echo(click.style("Changes to apply:", fg="cyan", bold=True), err=True)
        output_data(payload, output_format if output_format != "text" else "yaml")
        click.echo("", err=True)
        
        click.echo(click.style(f"✓ [DRY RUN] Would update issue: {issue_key}", fg="green", bold=True))
        if ctx.client.base_url:
            browse_url = f"{ctx.client.base_url.replace('/rest/api/3', '')}/browse/{issue_key}"
            click.echo(f"  URL: {browse_url}")
    else:
        # Actually update the issue
        ctx.client.update_issue(
            issue_key=issue_key,
            summary=summary,
            description=description,
            assignee=assignee,
            priority=priority,
            labels=list(labels) if labels else None,
            components=list(components) if components else None,
            extra_fields=translated_extra_fields,
        )
        
        if output_format == "text":
            click.echo(click.style(f"✓ Updated issue: {issue_key}", fg="green", bold=True))
            if ctx.client.base_url:
                browse_url = f"{ctx.client.base_url.replace('/rest/api/3', '')}/browse/{issue_key}"
                click.echo(f"  URL: {browse_url}")
        else:
            output = {
                "key": issue_key,
                "updated": True,
            }
            output_data(output, output_format)
