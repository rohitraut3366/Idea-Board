"""Plan generated sizing with native Terraform provider mocks, without cloud credentials."""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recommendations import recommendation  # noqa: E402

from config import Target, terraform_variables  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cloud", required=True, choices=("aws", "gcp"))
    parser.add_argument("--terraform", default="terraform")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3] / "infra/terraform" / args.cloud
    with tempfile.TemporaryDirectory(prefix="idea-board-sizing-") as directory:
        for environment in ("staging", "production"):
            proposal = recommendation(args.cloud, environment)
            if environment == "production":
                proposal["infrastructure"].update(
                    node_count=4,
                    node_size="t3.large" if args.cloud == "aws" else "e2-standard-4",
                    database_size="db.t4g.medium" if args.cloud == "aws" else "db-custom-2-7680",
                    database_storage_gb=40,
                )
            target = Target(args.cloud, environment, "a" * 40, "a" * 40)
            variables = Path(directory) / "sizing.tfvars.json"
            variables.write_text(json.dumps(terraform_variables(target, proposal)))
            subprocess.run(
                [args.terraform, f"-chdir={root}", "test", f"-var-file={variables}"], check=True
            )


if __name__ == "__main__":
    main()
