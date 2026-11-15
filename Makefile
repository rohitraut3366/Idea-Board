PYTHON ?= python3
TERRAFORM ?= terraform
export TERRAFORM

.DEFAULT_GOAL := help
.PHONY: help init plan apply output destroy state validate test

help:
	@echo 'make init|plan|apply|output|destroy|state|validate|test PROJECT=aws/staging/ap-southeast-2/networking'
	@echo 'Pass additional Terraform arguments with ARGS="...".'

init plan apply output destroy state validate test:
	@$(PYTHON) tools/terraform/project.py $@ "$(PROJECT)" -- $(ARGS)
