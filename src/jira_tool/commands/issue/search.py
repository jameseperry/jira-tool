"""Issue search subcommand."""

import click

from jira_tool.commands.issue import (
    issue,
    format_options,
    handle_api_errors,
    build_jql_query,
    format_issues_compact,
    format_issues_csv,
    output_data,
    simplify_issue,
    filter_fields,
    parse_fields_option,
    DEFAULT_FIELDS_SEARCH,
)


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
