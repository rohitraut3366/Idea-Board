"""Load locally built images into kind using the node's containerd settings."""

import argparse
import subprocess
import tempfile
import tomllib
from pathlib import Path


def output(*command):
    return subprocess.check_output(command, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="idea-board", help="kind cluster name")
    parser.add_argument("images", nargs="+")
    args = parser.parse_args()
    nodes = output("kind", "get", "nodes", "--name", args.name).splitlines()
    if not nodes:
        parser.error(f"No nodes found in kind cluster {args.name}")

    with tempfile.TemporaryDirectory(prefix="idea-board-images-") as directory:
        archive = Path(directory) / "images.tar"
        subprocess.run(["docker", "save", "-o", str(archive), *args.images], check=True)
        for node in nodes:
            plugins = tomllib.loads(
                output("docker", "exec", node, "containerd", "config", "dump")
            )["plugins"]
            snapshotter = plugins["io.containerd.cri.v1.images"]["snapshotter"]
            architecture = output("docker", "exec", node, "uname", "-m")
            platform = {"aarch64": "linux/arm64", "x86_64": "linux/amd64"}[architecture]
            print(f"Loading images into {node} ({platform}, {snapshotter})", flush=True)
            with archive.open("rb") as source:
                subprocess.run(
                    [
                        "docker",
                        "exec",
                        "-i",
                        node,
                        "ctr",
                        "--namespace",
                        "k8s.io",
                        "images",
                        "import",
                        "--local",
                        "--platform",
                        platform,
                        "--snapshotter",
                        snapshotter,
                        "-",
                    ],
                    stdin=source,
                    check=True,
                )
            for image in args.images:
                output("docker", "exec", node, "crictl", "inspecti", image)
                print(f"Ready on {node}: {image}", flush=True)


if __name__ == "__main__":
    main()
