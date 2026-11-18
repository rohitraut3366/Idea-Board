"""Prepare the diagnosis prompt or validate and publish the model's evidence-backed advice."""

import argparse
import json
import os
from pathlib import Path

from diagnosis import build_diagnosis_prompt, validate_diagnosis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prompt", "report"))
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--diagnosis", type=Path)
    arguments = parser.parse_args()
    rollout_evidence = json.loads(arguments.evidence.read_text())
    if arguments.command == "prompt":
        print(build_diagnosis_prompt(rollout_evidence))
    else:
        if not arguments.diagnosis:
            parser.error("report requires --diagnosis")
        diagnosis = validate_diagnosis(
            json.loads(arguments.diagnosis.read_text()), rollout_evidence
        )
        # Keep untrusted model prose out of workflow outputs and executable commands.
        diagnosis_markdown = "# Rollout diagnosis\n\n" + json.dumps(diagnosis, indent=2) + "\n"
        Path("diagnosis.md").write_text(diagnosis_markdown)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as summary_file:
                summary_file.write("\nSee the validated diagnosis artifact for rollout analysis.\n")


if __name__ == "__main__":
    main()
