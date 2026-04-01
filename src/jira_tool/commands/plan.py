"""Plan commands - generate scripts for complex operations."""

import click
from datetime import datetime

from jira_tool.client import JiraError


@click.group()
def plan():
    """Generate executable scripts for complex operations."""
    pass


@plan.command("project-merge")
@click.argument("output_file", required=False)
@click.option("--merge-from", "-f", "source_project", required=True, help="Source project key to merge from")
@click.option("--merge-into", "-i", "target_project", required=True, help="Target project key to merge into")
@click.option("--component", "-c", "components", multiple=True, help='Migrate components (use "NewName=OldName" to rename, or just "Name" to keep same)')
@click.option("--skip-boards", is_flag=True, default=False, help="Don't recreate boards in target project")
@click.option("--no-dry-run", is_flag=True, default=False, help="Generate script without dry-run mode (execute immediately)")
@click.pass_obj
def project_merge(
    ctx,
    output_file: str | None,
    source_project: str,
    target_project: str,
    components: tuple[str, ...],
    skip_boards: bool,
    no_dry_run: bool
):
    """Generate a migration script to merge one project into another.

    This analyzes the source project and generates a bash script that will:
    1. Create necessary components in the target project
    2. Move all issues from source to target (with component mapping)
    3. Recreate boards in the target project (with updated JQL)

    The generated script starts in DRY-RUN mode for safety. Review it,
    then comment out the JIRA_TOOL_DRY_RUN line to execute.

    \b
    Examples:
      # Generate migration script to file (starts in dry-run mode)
      jira-tool plan project-merge migrate.sh -f OLDPROJ -i NEWPROJ

      # Generate to stdout
      jira-tool plan project-merge -f OLDPROJ -i NEWPROJ

      # Execute immediately (no dry-run)
      jira-tool plan project-merge -f OLDPROJ -i NEWPROJ --no-dry-run | sh

      # Only migrate specific components
      jira-tool plan project-merge migrate.sh -f OLDPROJ -i NEWPROJ -c ComponentName

      # Rename components during migration
      jira-tool plan project-merge migrate.sh -f OLDPROJ -i NEWPROJ -c "NewName=OldName" -c "API=Backend API"

      # Skip board recreation
      jira-tool plan project-merge migrate.sh -f OLDPROJ -i NEWPROJ --skip-boards
    """
    try:
        # Gather information from source project
        click.echo(f"# Analyzing source project: {source_project}...", err=True)

        # Parse component specifications (NewName=OldName or just Name)
        component_mapping = {}  # old_name -> new_name
        source_component_names = []  # Which components to migrate

        if components:
            for comp_spec in components:
                if "=" in comp_spec:
                    # Rename: NewName=OldName
                    new_name, old_name = comp_spec.split("=", 1)
                    new_name = new_name.strip()
                    old_name = old_name.strip()
                    component_mapping[old_name] = new_name
                    source_component_names.append(old_name)
                else:
                    # Keep same name
                    name = comp_spec.strip()
                    component_mapping[name] = name
                    source_component_names.append(name)

        # Get components
        all_components = ctx.client.get_project_components(source_project)
        if source_component_names:
            # Filter to specific components
            source_components = [c for c in all_components if c.get("name") in source_component_names]
            if len(source_components) != len(source_component_names):
                found = {c.get("name") for c in source_components}
                missing = set(source_component_names) - found
                click.echo(f"# Warning: Components not found: {', '.join(missing)}", err=True)
        else:
            # No filter - migrate all and keep names
            source_components = all_components
            component_mapping = {c.get("name", ""): c.get("name", "") for c in all_components}

        click.echo(f"# Found {len(source_components)} components to migrate", err=True)

        # Get boards if not skipping
        source_boards = []
        if not skip_boards:
            source_boards = ctx.client.get_boards(project_key=source_project, max_results=100)
            # Filter boards if specific components requested
            if components:
                # We'll still include all boards, but note which ones might need JQL adjustment
                pass
            click.echo(f"# Found {len(source_boards)} boards to recreate", err=True)

        # Get issues to migrate (we'll use JQL in the script, not fetch them all now)
        # Just validate the projects exist
        try:
            ctx.client.get_project(source_project)
            ctx.client.get_project(target_project)
        except JiraError as e:
            click.echo(click.style(f"Error: {e}", fg="red"), err=True)
            raise SystemExit(1)

        click.echo(f"# Generating migration script...", err=True)

    except JiraError as e:
        click.echo(click.style(e.format_error(), fg="red"), err=True)
        raise SystemExit(1)

    # Generate the script
    script_lines = []

    # Header
    script_lines.append("#!/bin/bash")
    script_lines.append("set -e  # Exit on error")
    script_lines.append("")
    script_lines.append("# =============================================================================")
    script_lines.append(f"# JIRA Project Migration Script")
    script_lines.append(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    script_lines.append(f"# Source: {source_project}")
    script_lines.append(f"# Target: {target_project}")
    if components:
        script_lines.append(f"# Components: {', '.join(components)}")
    script_lines.append("# =============================================================================")
    script_lines.append("")
    script_lines.append("# SAFETY: Remove or comment out this line when ready to execute for real")
    script_lines.append("export JIRA_TOOL_DRY_RUN=1")
    script_lines.append("")
    script_lines.append(f'echo "=== JIRA Migration: {source_project} → {target_project} ==="')
    script_lines.append('echo "Dry-run mode: ${JIRA_TOOL_DRY_RUN:-disabled}"')
    script_lines.append('echo ""')
    script_lines.append("")

    # Step 1: Create components
    if source_components:
        script_lines.append("# =============================================================================")
        script_lines.append("# Step 1: Create components in target project")
        script_lines.append("# =============================================================================")
        script_lines.append('echo "Step 1: Creating components..."')
        script_lines.append("")

        for comp in source_components:
            old_name = comp.get("name", "")
            new_name = component_mapping.get(old_name, old_name)
            description = comp.get("description", "")
            lead_id = comp.get("lead", {}).get("accountId") if comp.get("lead") else None
            assignee_type = comp.get("assigneeType", "")

            cmd = f'jira-tool component create {target_project} "{new_name}"'
            if description:
                # Escape quotes in description
                escaped_desc = description.replace('"', '\\"')
                cmd += f' -d "{escaped_desc}"'
            if lead_id:
                cmd += f' -l {lead_id}'
            if assignee_type and assignee_type != "PROJECT_DEFAULT":
                cmd += f' -a {assignee_type}'

            script_lines.append(cmd)

        script_lines.append("")
        script_lines.append('echo ""')
        script_lines.append("")

    # Step 2: Move issues
    script_lines.append("# =============================================================================")
    script_lines.append("# Step 2: Move issues from source to target")
    script_lines.append("# =============================================================================")
    script_lines.append('echo "Step 2: Moving issues..."')
    script_lines.append("")

    if source_components:
        # Build component mapping argument (new_name=old_name)
        comp_map_args = []
        for comp in source_components:
            old_name = comp.get("name", "")
            new_name = component_mapping.get(old_name, old_name)
            comp_map_args.append(f'--map-component "{new_name}={old_name}"')
        comp_map_str = " ".join(comp_map_args)

        # For each component, get and move its issues
        for comp in source_components:
            old_name = comp.get("name", "")
            new_name = component_mapping.get(old_name, old_name)
            script_lines.append(f'# Moving issues in component: {old_name}')
            if old_name != new_name:
                script_lines.append(f'# (will be renamed to: {new_name})')
            script_lines.append(f'ISSUES=$(jira-tool issue search --project {source_project} --component "{old_name}" --list)')
            script_lines.append('for issue in $ISSUES; do')
            script_lines.append(f'  echo "  Moving $issue..."')
            script_lines.append(f'  jira-tool issue move "$issue" {target_project} {comp_map_str}')
            script_lines.append('done')
            script_lines.append("")
    else:
        # Move all issues without component filter
        script_lines.append(f'ISSUES=$(jira-tool issue search --project {source_project} --list)')
        script_lines.append('for issue in $ISSUES; do')
        script_lines.append(f'  echo "  Moving $issue..."')
        script_lines.append(f'  jira-tool issue move "$issue" {target_project}')
        script_lines.append('done')
        script_lines.append("")

    script_lines.append('echo ""')
    script_lines.append("")

    # Step 3: Recreate boards
    if source_boards and not skip_boards:
        script_lines.append("# =============================================================================")
        script_lines.append("# Step 3: Recreate boards in target project")
        script_lines.append("# =============================================================================")
        script_lines.append('echo "Step 3: Recreating boards..."')
        script_lines.append("")

        for board in source_boards:
            board_id = board.get("id")
            board_name = board.get("name", "")
            board_type = board.get("type", "scrum")

            # Try to get the filter for this board
            try:
                # Use the configuration endpoint to get filter info
                board_config = ctx.client.get_board_configuration(board_id)
                filter_id = board_config.get("filter", {}).get("id")
                if filter_id:
                    filter_info = ctx.client.get_filter(filter_id)
                    original_jql = filter_info.get("jql", "")

                    # Update JQL to use target project
                    updated_jql = original_jql.replace(f'project = {source_project}', f'project = {target_project}')
                    updated_jql = updated_jql.replace(f'project = "{source_project}"', f'project = "{target_project}"')
                    updated_jql = updated_jql.replace(f'project={source_project}', f'project={target_project}')

                    # Update component names in JQL if they were renamed
                    for old_name, new_name in component_mapping.items():
                        if old_name != new_name:
                            # Replace component references in JQL
                            updated_jql = updated_jql.replace(f'component = "{old_name}"', f'component = "{new_name}"')
                            updated_jql = updated_jql.replace(f"component = '{old_name}'", f"component = '{new_name}'")

                    # Escape quotes for bash
                    escaped_jql = updated_jql.replace('"', '\\"')

                    script_lines.append(f'# Board: {board_name} (was ID: {board_id})')
                    script_lines.append(f'jira-tool board create "{board_name} (migrated)" \\')
                    script_lines.append(f'  --filter-jql "{escaped_jql}" \\')
                    script_lines.append(f'  --type {board_type}')
                    script_lines.append("")
                else:
                    # No filter ID found - likely a Company-managed board
                    script_lines.append(f'# Board: {board_name} (ID: {board_id})')
                    script_lines.append(f'# NOTE: This appears to be a Company-managed board (no JQL filter).')
                    script_lines.append(f'#       Company-managed boards cannot be automatically migrated.')
                    script_lines.append(f'#       You will need to manually recreate this board in {target_project}.')
                    script_lines.append("")
            except JiraError as e:
                # If we can't get filter, just add a comment with error detail
                click.echo(f"# Warning: Could not fetch filter for board {board_name} (ID: {board_id}): {e}", err=True)
                script_lines.append(f'# Board: {board_name} (ID: {board_id}) - could not fetch filter, create manually')
                script_lines.append("")

        script_lines.append('echo ""')
        script_lines.append("")

    # Footer
    script_lines.append("# =============================================================================")
    script_lines.append('echo "=== Migration complete! ==="')
    script_lines.append('echo ""')
    script_lines.append('echo "NOTE: Review the results and verify everything migrated correctly."')
    script_lines.append(f'echo "      Issues have new keys in {target_project}."')
    script_lines.append(f'echo "      You may want to archive the {source_project} project after verification."')

    # Conditionally remove dry-run line if --no-dry-run specified
    if no_dry_run:
        # Remove the dry-run export line
        script_lines = [line for line in script_lines if not line.startswith("export JIRA_TOOL_DRY_RUN")]
        script_lines = [line for line in script_lines if "SAFETY: Remove or comment" not in line]

    # Write the script
    script = "\n".join(script_lines)

    if output_file:
        # Write to file
        with open(output_file, 'w') as f:
            f.write(script)
            f.write("\n")
        click.echo(f"# Migration script written to: {output_file}", err=True)
        click.echo(f"# Review the script, then run: bash {output_file}", err=True)
    else:
        # Write to stdout
        print(script)
