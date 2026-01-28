"""Field-related CLI commands."""

import click

from jira_tool.client import JiraError
from jira_tool.formatting import output_data


@click.group()
def field():
    """Commands for working with JIRA fields."""
    pass


@field.command("list")
@click.option("--search", "-q", default=None, help="Filter fields by name (case-insensitive)")
@click.option("--custom-only", is_flag=True, default=False, help="Show only custom fields")
@click.option("--json", "output_format", flag_value="json", help="Output as JSON")
@click.option("--yaml", "output_format", flag_value="yaml", help="Output as YAML")
@click.pass_obj
def field_list(ctx, search: str | None, custom_only: bool, output_format: str | None):
    """List available JIRA fields.
    
    Shows field names and their IDs, useful for using --field in issue create.
    
    \b
    Examples:
      # List all fields
      jira-tool field list
      
      # Search for severity-related fields
      jira-tool field list -q severity
      
      # Show only custom fields
      jira-tool field list --custom-only
    """
    try:
        fields = ctx.client.get_fields()
    except JiraError as e:
        click.echo(click.style(e.format_error(), fg="red"), err=True)
        raise SystemExit(1)
    
    # Filter by search term
    if search:
        search_lower = search.lower()
        fields = [f for f in fields if search_lower in f.get("name", "").lower() or search_lower in f.get("id", "").lower()]
    
    # Filter to custom fields only
    if custom_only:
        fields = [f for f in fields if f.get("custom", False)]
    
    # Sort by name
    fields = sorted(fields, key=lambda f: f.get("name", "").lower())
    
    if output_format:
        # JSON/YAML output
        simplified = [
            {
                "id": f.get("id", ""),
                "name": f.get("name", ""),
                "custom": f.get("custom", False),
                "type": f.get("schema", {}).get("type", "unknown") if f.get("schema") else "unknown",
            }
            for f in fields
        ]
        output_data(simplified, output_format)
    else:
        # Table output
        if not fields:
            click.echo("No fields found.")
            return
        
        click.echo(click.style(f"{'Field Name':<40} {'Field ID':<25} {'Type':<15} {'Custom'}", fg="cyan", bold=True))
        click.echo("─" * 90)
        
        for f in fields:
            name = f.get("name", "")[:39]
            field_id = f.get("id", "")[:24]
            schema = f.get("schema", {}) or {}
            field_type = schema.get("type", "unknown")[:14]
            is_custom = "✓" if f.get("custom", False) else ""
            
            click.echo(f"{name:<40} {field_id:<25} {field_type:<15} {is_custom}")
        
        click.echo("")
        click.echo(f"Total: {len(fields)} fields")


@field.command("options")
@click.argument("project")
@click.argument("issue_type")
@click.option("--field", "-f", "field_name", default=None, help="Show options for a specific field only")
@click.option("--json", "output_format", flag_value="json", help="Output as JSON")
@click.option("--yaml", "output_format", flag_value="yaml", help="Output as YAML")
@click.pass_obj
def field_options(ctx, project: str, issue_type: str, field_name: str | None, output_format: str | None):
    """Show available field options for a project/issue type.
    
    Uses the createmeta API to show allowed values for fields.
    
    \b
    Examples:
      # Show all fields with options for Bug in PROJ
      jira-tool field options PROJ Bug
      
      # Show options for Severity field only
      jira-tool field options PROJ Bug -f Severity
    """
    try:
        # Get all issue types to find the ID
        all_issue_types = ctx.client.get("issuetype")
        issue_type_id = None
        for it in all_issue_types:
            if it.get("name", "").lower() == issue_type.lower():
                issue_type_id = it.get("id")
                break
        
        if not issue_type_id:
            click.echo(click.style(f"Issue type '{issue_type}' not found", fg="red"), err=True)
            raise SystemExit(1)
        
        # Get createmeta for this project/issue type
        meta = ctx.client.get(f"issue/createmeta/{project}/issuetypes/{issue_type_id}", params={"maxResults": 100})
        fields_meta = meta.get("fields", [])
        
        # Build field name mapping for lookups
        field_map = {}
        for fm in fields_meta:
            field_map[fm.get("fieldId", "").lower()] = fm
            field_map[fm.get("key", "").lower()] = fm
            field_map[fm.get("name", "").lower()] = fm
        
        # Filter to specific field if requested
        if field_name:
            fm = field_map.get(field_name.lower())
            if not fm:
                click.echo(click.style(f"Field '{field_name}' not found for {project}/{issue_type}", fg="red"), err=True)
                raise SystemExit(1)
            fields_meta = [fm]
        
        # Filter to only fields with allowedValues
        fields_with_options = [f for f in fields_meta if f.get("allowedValues")]
        
        if output_format:
            simplified = [
                {
                    "id": f.get("fieldId") or f.get("key", ""),
                    "name": f.get("name", ""),
                    "required": f.get("required", False),
                    "allowedValues": [
                        {"value": v.get("value", v.get("name", v.get("id", ""))), "id": v.get("id", "")} 
                        for v in f.get("allowedValues", [])
                    ],
                }
                for f in fields_with_options
            ]
            output_data(simplified, output_format)
        else:
            if not fields_with_options:
                click.echo("No fields with predefined options found.")
                return
            
            for f in fields_with_options:
                name = f.get("name", "")
                field_id = f.get("fieldId") or f.get("key", "")
                required = "required" if f.get("required", False) else "optional"
                
                click.echo(click.style(f"\n{name}", fg="cyan", bold=True) + f" ({field_id}) [{required}]")
                click.echo("─" * 50)
                
                allowed = f.get("allowedValues", [])
                for v in allowed:
                    # Different fields store values differently
                    value = v.get("value") or v.get("name") or v.get("id", "")
                    vid = v.get("id", "")
                    if vid and vid != value:
                        click.echo(f"  • {value} (id: {vid})")
                    else:
                        click.echo(f"  • {value}")
            
            click.echo("")
            
    except JiraError as e:
        click.echo(click.style(e.format_error(), fg="red"), err=True)
        raise SystemExit(1)
