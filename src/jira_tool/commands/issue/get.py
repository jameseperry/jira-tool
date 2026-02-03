"""Issue get subcommand."""

import click

from jira_tool.commands.issue import (
    issue,
    format_options,
    handle_api_errors,
    output_data,
    filter_custom_fields,
    simplify_issue,
    filter_fields,
    parse_fields_option,
    DEFAULT_FIELDS_GET,
)


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
            # Use rich markup only for human-readable text output
            use_rich = output_format == "text"
            simplified = simplify_issue(issue, comments=issue_comments, children=children_issues, use_rich_markup=use_rich)
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
