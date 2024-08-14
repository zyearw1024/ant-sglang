"""Launch the inference server."""
from sglang.patch.monkey_patch_launch_server import patch_all; patch_all()
import argparse

from sglang.srt.server import launch_server
from sglang.srt.server_args import ServerArgs

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    ServerArgs.add_cli_args(parser)
    args = parser.parse_args()
    server_args = ServerArgs.from_cli_args(args)

    launch_server(server_args)
