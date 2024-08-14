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


async def _fastapi_before_request_hook_v1_completions(request: Request):
    """Hook function to modify request data for /v1/chat/completions endpoint."""
    if not get_stream_include_usage_status():
        return

    # Retrieve JSON data from the request
    json_data = await request.json()

    # Ensure "include_usage" is set to True in "stream_options"
    if "stream_options" not in json_data:
        json_data["stream_options"] = {"include_usage": True}
    elif "include_usage" not in json_data["stream_options"]:
        json_data["stream_options"]["include_usage"] = True

    # Store modified JSON data for use in subsequent request handling
    request.state.modified_json = json_data


def patch_api_route(self, path: str, *, dependencies=None, **kwargs):
    """Patch the API route to add dependencies for specific paths."""
    if "/v1/chat/completions" in path and dependencies is None:
        dependencies = [Depends(_fastapi_before_request_hook_v1_completions)]

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
    return parser


def patch_all():
    """Apply patches to the necessary components."""
    APIRouter._super_api_route = APIRouter.api_route
    APIRouter.api_route = patch_api_route

    ArgumentParser._origin_parse_args = ArgumentParser.parse_args
    ArgumentParser.parse_args = _patch_parse_args
