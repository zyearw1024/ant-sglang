from argparse import ArgumentParser
from functools import cache

from fastapi import Depends, Request
from fastapi.routing import APIRouter


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
def get_qwen3_enable_thinking_status():
    """Check if the qwen3 thinking option is enabled via CLI arguments."""
    args = CLIContext.args
    if not args:
        return None  # Return None if no arguments are provided
    return getattr(args, "qwen3_enable_thinking", False)


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

    # Handle qwen3_enable_thinking based on command line argument and model name
    enable_thinking_by_cli = get_qwen3_enable_thinking_status()
    model_name = json_data.get("model", "")
    enable_thinking_by_model_name_suffix = model_name.endswith("-think")

    enable_thinking = False
    if enable_thinking_by_cli:
        if enable_thinking_by_model_name_suffix:
            enable_thinking = True
            # Remove the -think suffix from the model name
            json_data["model"] = model_name.rstrip("-think")

        if "chat_template_kwargs" not in json_data:
            json_data["chat_template_kwargs"] = {"enable_thinking": enable_thinking}
        elif "enable_thinking" not in json_data["chat_template_kwargs"]:
            json_data["chat_template_kwargs"]["enable_thinking"] = enable_thinking
        else:
            json_data["chat_template_kwargs"]["enable_thinking"] = enable_thinking

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

    parser.add_argument(
        "--qwen3-enable-thinking",
        action="store_true",
        default=False,
        help="Enable Qwen3 thinking mode. Default: off. Thinking can be enabled by this argument or by appending '-think' to the model name in the request."
    )
    return parser


def patch_all():
    """Apply patches to the necessary components."""
    APIRouter._super_api_route = APIRouter.api_route
    APIRouter.api_route = patch_api_route

    ArgumentParser._origin_parse_args = ArgumentParser.parse_args
    ArgumentParser.parse_args = _patch_parse_args
