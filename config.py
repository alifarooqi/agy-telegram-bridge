import os
from dotenv import load_dotenv
from google.antigravity import LocalAgentConfig, CapabilitiesConfig
from google.antigravity.hooks import policy

# Load environment variables from .env file
load_dotenv()

# Telegram Settings
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Parse ALLOWED_TELEGRAM_USER_IDS as a set of ints
ALLOWED_TELEGRAM_USER_IDS = set()
allowed_users_raw = os.getenv("ALLOWED_TELEGRAM_USER_IDS", "")
if allowed_users_raw:
    for item in allowed_users_raw.split(","):
        item = item.strip()
        if item.isdigit():
            ALLOWED_TELEGRAM_USER_IDS.add(int(item))
        elif item.startswith("-") and item[1:].isdigit():
            ALLOWED_TELEGRAM_USER_IDS.add(int(item))

# System Instructions for the Agent
SYSTEM_INSTRUCTIONS = os.getenv(
    "SYSTEM_INSTRUCTIONS", 
    "You are an AI developer assistant running on the user's Mac. "
    "You can view files, search directories, and perform read-only tasks. "
    "For command execution, you are selectively allowed to run git commands (e.g., git status, git diff, git add, git commit). "
    "Other shell commands are denied by safety policies."
)

def _is_git_command(args: dict) -> bool:
    """Predicate to check if a run_command tool call is a git command."""
    cmd_line = args.get("CommandLine", "").strip()
    # Accept if the command is exactly 'git' or starts with 'git '
    return cmd_line == "git" or cmd_line.startswith("git ")

def get_agent_config(project_dir: str | None = None) -> LocalAgentConfig:
    """Creates and returns the LocalAgentConfig based on environment variables."""
    api_key = os.getenv("GEMINI_API_KEY")
    
    # Configure capabilities
    capabilities = CapabilitiesConfig(
        enable_subagents=True
    )
    
    # Safety Policies:
    # 1. Deny all tools by default (fallback)
    # 2. Allow all read-only tools
    # 3. Allow run_command ONLY for git commands
    # 4. Allow search_web
    policies = [
        policy.deny_all(),
        # Read-only tools
        policy.allow("list_directory"),
        policy.allow("search_directory"),
        policy.allow("find_file"),
        policy.allow("view_file"),
        policy.allow("read_url_content"),
        policy.allow("finish"),
        # Web search
        policy.allow("search_web"),
        # Git commands only
        policy.allow("run_command", when=_is_git_command, name="allow_git_commands")
    ]
    
    # Set workspaces list if a specific project directory is provided
    workspaces = [project_dir] if project_dir else None
    
    return LocalAgentConfig(
        system_instructions=SYSTEM_INSTRUCTIONS,
        capabilities=capabilities,
        policies=policies,
        api_key=api_key,
        workspaces=workspaces
    )
