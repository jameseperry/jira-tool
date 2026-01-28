# jira-tool

A command-line interface for interacting with JIRA Cloud API.

## Features

- Fetch issue details with simplified, human-readable output
- Search issues using JQL or convenient filter options
- Create and edit issues with custom field support
- Discover fields and allowed values for any project/issue type
- Multiple output formats: text (Rich tables/panels), JSON, YAML, CSV
- Color-coded status, priority, and issue types
- Automatic fetching of child issues for epics
- Comment viewing support

## Installation

### Using pipx (Recommended)

[pipx](https://pipx.pypa.io/) installs the tool in an isolated environment while making it available globally:

```bash
# Install pipx if you don't have it
pip install --user pipx
pipx ensurepath  # restart your shell after this

# Install jira-tool
pipx install git+https://github.com/jameseperry/jira-tool.git

# Or from a local clone
pipx install /path/to/jira-tool

# For development (editable install - picks up code changes)
pipx install -e /path/to/jira-tool
```

### Using pip

```bash
# Install globally (not recommended)
pip install git+https://github.com/jameseperry/jira-tool.git

# Or in a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install git+https://github.com/jameseperry/jira-tool.git
```

### From Source (Development)

```bash
git clone https://github.com/jameseperry/jira-tool.git
cd jira-tool
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configuration

Authentication is configured via environment variables:

```bash
export JIRA_BASE_URL="https://yourcompany.atlassian.net"
export JIRA_EMAIL="your.email@company.com"
export JIRA_API_TOKEN="your-api-token"
```

To generate an API token, visit: https://id.atlassian.com/manage-profile/security/api-tokens

You can also pass these as command-line options (`--base-url`, `--email`, `--token`), but environment variables are recommended.

### Optional

```bash
export JIRA_DEBUG=1  # Enable debug output on errors
```

## Usage

### Get Issue Details

Fetch one or more issues by key:

```bash
# Single issue
jira-tool issue get PROJ-123

# Multiple issues
jira-tool issue get PROJ-123 PROJ-124 PROJ-125

# Include comments
jira-tool issue get PROJ-123 --comments

# Output as JSON
jira-tool issue get PROJ-123 --json

# Output as YAML
jira-tool issue get PROJ-123 --yaml

# Raw API response (for debugging)
jira-tool issue get PROJ-123 --raw --include-custom-fields
```

### Field Selection

Control which fields are included in the output with `--fields`:

```bash
# Only specific fields
jira-tool issue get PROJ-123 --fields key,summary,status --yaml

# Add fields to defaults (use + prefix)
jira-tool issue get PROJ-123 --fields +labels,+time_tracking --yaml

# Remove fields from defaults (use - prefix)
jira-tool issue get PROJ-123 --fields -components,-created --yaml

# All available fields
jira-tool issue get PROJ-123 --fields all --yaml

# Works with search too
jira-tool issue search -p PROJ -a me --fields key,summary,status,labels --yaml
```

**Available fields:** `key`, `id`, `summary`, `description`, `status`, `type`, `priority`, `resolution`, `assignee`, `reporter`, `created`, `updated`, `due_date`, `labels`, `components`, `fix_versions`, `project`, `parent`, `time_tracking`, `subtasks`, `links`, `children`, `comments`

### Search Issues

Search using convenient filter options:

```bash
# Find your open issues in a project
jira-tool issue search --project PROJ --assignee me

# Find issues by status
jira-tool issue search --project PROJ --status "In Progress"

# Find bugs updated in the last week
jira-tool issue search --type Bug --updated-after -7d

# Find high priority issues
jira-tool issue search --project PROJ --priority "P1: High"

# Full-text search
jira-tool issue search --text "memory leak" --project PROJ

# Combine multiple filters
jira-tool issue search \
  --project PROJ \
  --assignee me \
  --type Story \
  --status "In Progress" \
  --updated-after -30d

# Use raw JQL for complex queries
jira-tool issue search --jql "project = PROJ AND status = Open ORDER BY created DESC"
```

#### Search Filter Options

| Option | Description |
|--------|-------------|
| `--project`, `-p` | Project key |
| `--component`, `-c` | Component name (can specify multiple) |
| `--assignee`, `-a` | Assignee (use `me` for yourself, `unassigned` for none) |
| `--reporter` | Reporter (use `me` for yourself) |
| `--status`, `-s` | Status (can specify multiple) |
| `--type` | Issue type: Bug, Story, Task, Epic, Sub-task |
| `--priority` | Priority level |
| `--label` | Label (can specify multiple) |
| `--fix-version` | Fix version (can specify multiple) |
| `--parent` | Parent issue key (for epic children or subtasks) |
| `--created-after` | Created after date (YYYY-MM-DD or -7d for relative) |
| `--created-before` | Created before date |
| `--updated-after` | Updated after date |
| `--updated-before` | Updated before date |
| `--text`, `-q` | Full-text search |
| `--allow-closed` | Include Done/Closed issues (excluded by default) |
| `--order-by` | Sort order (default: `updated DESC`) |
| `--limit` | Maximum results (default: 50) |
| `--show-jql` | Print the generated JQL query |

### Get Child Issues

Fetch all children of an epic or parent issue:

```bash
jira-tool issue children PROJ-100

# Output as list of keys (for scripting)
jira-tool issue children PROJ-100 --list
```

### Create Issues

Create new JIRA issues:

```bash
# Create a simple task
jira-tool issue create -p PROJ -s "Fix login bug"

# Create a bug with description
jira-tool issue create -p PROJ -s "Login fails" --type Bug -d "Users cannot log in"

# Create issue with labels and components
jira-tool issue create -p PROJ -s "New feature" --label backend --label api --component Backend

# Create a sub-task under a parent
jira-tool issue create -p PROJ -s "Sub-task" --type Sub-task --parent PROJ-123

# Create a story under an epic
jira-tool issue create -p PROJ -s "User story" --type Story --parent PROJ-100

# Use custom fields by name (auto-translated to field IDs)
jira-tool issue create -p PROJ -s "Critical bug" --type Bug \
  --field "Severity=Critical" --field "Steps to Reproduce=1. Do X\n2. Do Y"

# Dry-run to see what would be created
jira-tool issue create -p PROJ -s "Test issue" --dry-run
```

#### Create Options

| Option | Description |
|--------|-------------|
| `--project`, `-p` | Project key (required) |
| `--summary`, `-s` | Issue summary/title (required) |
| `--type` | Issue type (default: Task) |
| `--description`, `-d` | Issue description |
| `--assignee`, `-a` | Assignee account ID or email |
| `--priority` | Priority name (e.g., 'P1: High') |
| `--label` | Label (can specify multiple) |
| `--component` | Component name (can specify multiple) |
| `--parent` | Parent issue key (for sub-tasks or epic children) |
| `--field` | Custom field in 'name=value' format (can specify multiple) |
| `--dry-run` | Show what would be created without creating |

### Edit Issues

Update existing JIRA issues:

```bash
# Update summary
jira-tool issue edit PROJ-123 -s "New title"

# Update description
jira-tool issue edit PROJ-123 -d "Updated description"

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
```

#### Edit Options

| Option | Description |
|--------|-------------|
| `--summary`, `-s` | New issue summary/title |
| `--description`, `-d` | New issue description |
| `--assignee`, `-a` | New assignee (use '' to unassign) |
| `--priority` | New priority name |
| `--label` | Set labels (replaces existing, can specify multiple) |
| `--component` | Set components (replaces existing, can specify multiple) |
| `--field` | Custom field in 'name=value' format (can specify multiple) |
| `--dry-run` | Show what would be changed without updating |

### Field Discovery

Discover available fields and their allowed values:

```bash
# List all fields (searchable by keyword)
jira-tool field list

# Search for specific fields
jira-tool field list --search severity
jira-tool field list --search "steps to reproduce"

# Show only custom fields
jira-tool field list --custom-only

# Get allowed values for a field (requires project and issue type)
jira-tool field options --project PROJ --type Bug --field Severity
jira-tool field options -p PROJ -t Bug -f "Steps to Reproduce"

# Output as JSON for scripting
jira-tool field list --search priority --json
jira-tool field options -p PROJ -t Bug -f Severity --json
```

Field discovery is useful when:
- You need to find the exact name of a custom field
- You want to see what values are allowed for a field
- You're setting up `--field` options for `issue create` or `issue edit`

### Output Formats

All commands support multiple output formats:

| Flag | Description |
|------|-------------|
| `--human` | Human-readable text with Rich formatting (default) |
| `--json` | JSON output |
| `--yaml` | YAML output |
| `--csv` | CSV output (best for search results) |
| `--list`, `-l` | Just issue keys, one per line (for scripting) |

### Scripting Examples

```bash
# Pipe issue keys to another command
jira-tool issue search -p PROJ -a me --list | xargs -I {} echo "Processing {}"

# Export search results to CSV
jira-tool issue search -p PROJ --updated-after -7d --csv > issues.csv

# Get issues as JSON for processing with jq
jira-tool issue search -p PROJ --json | jq '.[].key'
```

## Debug Mode

Enable debug mode for verbose error output including stack traces and raw API responses:

```bash
# Via environment variable
export JIRA_DEBUG=1
jira-tool issue get PROJ-123

# Via command-line flag
jira-tool --debug issue get PROJ-123
```

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/jira_tool
```

## License

MIT
