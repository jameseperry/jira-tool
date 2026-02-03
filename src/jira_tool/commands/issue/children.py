"""Issue children subcommand."""

import click

from jira_tool.commands.issue import (
    issue,
    format_options,
    handle_api_errors,
    format_issues_compact,
    format_issues_csv,
    output_data,
    simplify_issue,
    filter_fields,
    parse_fields_option,
    DEFAULT_FIELDS_SEARCH,
)


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
        # No rich markup for CSV output
        simplified = [filter_fields(simplify_issue(issue, use_rich_markup=False), selected_fields) for issue in issues]
        click.echo(format_issues_csv(simplified), nl=False)
    else:
        # No rich markup for JSON/YAML output
        simplified = [filter_fields(simplify_issue(issue, use_rich_markup=False), selected_fields) for issue in issues]
        output_data(simplified, output_format)
