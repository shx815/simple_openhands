# Common timeout message that can be used across different timeout scenarios
TIMEOUT_MESSAGE_TEMPLATE = (
    "You may wait longer to see additional output by sending empty command '', "
    'send other commands to interact with the current process, '
    'send keys ("C-c", "C-z", "C-d") to interrupt/kill the previous command before sending your new command, '
    'or use the timeout parameter in execute_bash for future commands.'
)

# Default timeout values
DEFAULT_COMMAND_TIMEOUT = 60  # seconds
DEFAULT_NO_CHANGE_TIMEOUT = 30  # seconds

# Exit codes
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_TIMEOUT = -1
EXIT_RUNNING = -1

# Command types
COMMAND_TYPE_SYNC = "sync"
COMMAND_TYPE_ASYNC = "async"
COMMAND_TYPE_BACKGROUND = "background"

# Control commands
CONTROL_CMD_INTERRUPT = "C-c"
CONTROL_CMD_SUSPEND = "C-z"
CONTROL_CMD_EOF = "C-d"

# Error messages
ERROR_NO_RUNNING_COMMAND = "ERROR: No previous running command to retrieve logs from."
ERROR_NO_COMMAND_TO_INTERACT = "ERROR: No previous running command to interact with."
ERROR_MULTIPLE_COMMANDS = "ERROR: Cannot execute multiple commands at once."
ERROR_COMMAND_PARSING = "ERROR: Command could not be parsed by PowerShell."

# Success messages
SUCCESS_BACKGROUND_JOB = "Command started as background job {job_id}."
SUCCESS_COMMAND_COMPLETED = "The command completed with exit code {exit_code}."

# Timeout messages
TIMEOUT_COMMAND_MESSAGE = "The command timed out after {timeout} seconds."
TIMEOUT_JOB_MESSAGE = "The command timed out after {timeout} seconds."

# Working directory messages
CWD_CHANGED = "Working directory changed to: {cwd}"
CWD_ERROR = "Failed to change working directory to: {cwd}"

# Job states
JOB_STATE_RUNNING = "Running"
JOB_STATE_COMPLETED = "Completed"
JOB_STATE_FAILED = "Failed"
JOB_STATE_STOPPED = "Stopped"
JOB_STATE_NOT_STARTED = "NotStarted"

# PowerShell specific constants
POWERSHELL_EXECUTION_POLICY = "Unrestricted"
POWERSHELL_DEFAULT_TIMEOUT = 30
POWERSHELL_MAX_OUTPUT_WIDTH = 4096

# File operations
FILE_READ_SUCCESS = "File read successfully"
FILE_WRITE_SUCCESS = "File written successfully"
FILE_DELETE_SUCCESS = "File deleted successfully"
FILE_NOT_FOUND = "File not found"
FILE_ACCESS_DENIED = "Access denied"

# Logging levels
LOG_LEVEL_DEBUG = "DEBUG"
LOG_LEVEL_INFO = "INFO"
LOG_LEVEL_WARNING = "WARNING"
LOG_LEVEL_ERROR = "ERROR"
LOG_LEVEL_CRITICAL = "CRITICAL"
