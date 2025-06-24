import logging
from argparse import ArgumentParser
from functools import cache
from typing import Optional

from fastapi import Depends, Request
from fastapi.routing import APIRouter

logger = logging.getLogger(__name__)


class CLIContext:
    args = None


@cache
def get_stream_include_usage_status():
    """Check if the stream usage option is enabled via CLI arguments."""
    args = CLIContext.args
    if not args:
        return None  # Return None if no arguments are provided
    return getattr(args, "enable_stream_include_usage", False)


@cache
def get_args_qwen3_enable_chat_template_thinking():
    """Get the status of Qwen3 chat template thinking mode (hard switch)."""
    try:
        args = CLIContext.args
        if args is None:
            return False
        # Enable if either new or old parameter is set
        chat_template_thinking = getattr(args, "qwen3_enable_chat_template_thinking", False)
        legacy_thinking = getattr(args, "qwen3_enable_thinking", False)
        return chat_template_thinking or legacy_thinking
    except:
        return False


@cache 
def get_qwen3_enable_thinking_status():
    """Check if the qwen3 thinking option is enabled via CLI arguments (legacy function for backward compatibility)."""
    args = CLIContext.args
    if not args:
        return None  # Return None if no arguments are provided
    return getattr(args, "qwen3_enable_thinking", False)


def _handle_qwen3_chat_template_thinking(json_data):
    """Handle Qwen3 chat template thinking logic (hard switch)."""
    try:
        model_name = json_data.get("model", "")
        
        # Check if user already provided enable_thinking parameter
        user_provided_enable_thinking = None
        if "chat_template_kwargs" in json_data and "enable_thinking" in json_data["chat_template_kwargs"]:
            user_provided_enable_thinking = json_data["chat_template_kwargs"]["enable_thinking"]
        
        # Determine default value based on model name
        _enable_think_default = False
        if model_name:
            _enable_think_default = model_name.endswith("-think")
            
            # # Remove the -think suffix from the model name
            # if model_name.endswith("-think"):
            #     json_data["model"] = model_name.rstrip("-think")

        # Set enable_thinking in chat_template_kwargs
        if "chat_template_kwargs" not in json_data:
            json_data["chat_template_kwargs"] = {}
        
        # Use user provided value if available, otherwise use default based on model name
        if user_provided_enable_thinking is not None:
            final_enable_thinking = user_provided_enable_thinking
        else:
            final_enable_thinking = _enable_think_default
        
        json_data["chat_template_kwargs"]["enable_thinking"] = final_enable_thinking

    except Exception as e:
        logger.error(f"Error processing qwen3 chat template thinking: {e}")


def handle_qwen3_thinking_modes(json_data):
    """
    Handle Qwen3 thinking mode logic.
    Default behavior: no thinking mode enabled unless explicitly requested.
    """
    try:
        qwen3_chat_template_thinking = get_args_qwen3_enable_chat_template_thinking()

        # Process thinking mode if enabled
        if qwen3_chat_template_thinking:
            _handle_qwen3_chat_template_thinking(json_data)
            return True
        else:
            # Default behavior: no thinking mode enabled
            return False

    except Exception as e:
        logger.error(f"Error handling qwen3 thinking modes: {e}")
        return False


async def _fastapi_before_request_hook_v1_completions(request: Request):
    """Hook function to modify request data for /v1/chat/completions endpoint."""
    json_data = await request.json()
    modified = False

    # Handle enable_stream_include_usage
    if get_stream_include_usage_status():
        if "stream_options" not in json_data:
            json_data["stream_options"] = {"include_usage": True}
        elif "include_usage" not in json_data["stream_options"]:
            json_data["stream_options"]["include_usage"] = True
        modified = True

    # Handle qwen3 thinking modes
    if handle_qwen3_thinking_modes(json_data):
        modified = True

    if modified:
        # Store modified JSON data for use in subsequent request handling
        request.state.modified_json = json_data


def patch_api_route(self, path: str, *, dependencies=None, **kwargs):
    """Patch the API route to add dependencies for specific paths."""
    if "/v1/chat/completions" in path:
        if dependencies is None:
            dependencies = []
        dependencies.append(Depends(_fastapi_before_request_hook_v1_completions))

    return self._super_api_route(path, dependencies=dependencies, **kwargs)


def _patch_parse_args(self, *args, **kwargs):
    """Patch the argument parser to include custom arguments."""
    _arg_parser_add_argument(self)

    args = self._origin_parse_args(*args, **kwargs)
    CLIContext.args = args
    return args


def _arg_parser_add_argument(parser):
    """Add custom arguments to the argument parser."""
    parser.add_argument(
        "--enable-stream-include-usage",
        action="store_true",
        help="Enable the inclusion of stream usage data in the output, useful for monitoring performance.",
    )

    # Backward compatibility: keep old parameter name
    parser.add_argument(
        "--qwen3-enable-thinking",
        action="store_true",
        default=False,
        help="[DEPRECATED] This option is for backward compatibility. Its functionality is now fully aligned with --qwen3-enable-chat-template-thinking. "
        "Enable Qwen3 thinking mode. If not set, will check environment variable QWEN3_ENABLE_THINKING. Default: off. "
        "If model name is Qwen3-1.7B, thinking is off by default. If model name is Qwen3-1.7B-think, thinking is on.",
    )

    parser.add_argument(
        "--qwen3-enable-chat-template-thinking",
        action="store_true",
        default=False,
        help="Enable Qwen3 chat template thinking mode (hard switch). "
        "When enabled, it will set request.enable_thinking "
        "if not specified in the request. "
        "Default: off.",
    )
    
    return parser


def patch_all():
    """Apply patches to the necessary components."""
    logger.info("Applying all monkey patches for SGLang")
    
    try:
        APIRouter._super_api_route = APIRouter.api_route
        APIRouter.api_route = patch_api_route
        logger.info("Successfully patched APIRouter")
    except Exception as e:
        logger.warning(f"Failed to patch APIRouter: {e}")

    try:
        # Store original method
        if not hasattr(ArgumentParser, "_origin_parse_args"):
            setattr(ArgumentParser, "_origin_parse_args", ArgumentParser.parse_args)
        ArgumentParser.parse_args = _patch_parse_args
        logger.info("Successfully patched ArgumentParser")
    except Exception as e:
        logger.warning(f"Failed to patch ArgumentParser: {e}")
