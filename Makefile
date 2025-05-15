.PHONY: clean
clean: clean-test clean-build clean-pyc clean-docs

.PHONY: clean-build
clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	rm -fr pip-wheel-metadata
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -fr {} +
	find . -type d -name __pycache__ -exec rm -rv {} +
	rm -fr Pipfile.lock
	rm -rf plugins/*/build
	rm -rf plugins/*/dist

.PHONY: clean-docs
clean-docs:
	rm -fr site/

.PHONY: clean-pyc
clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +
	find . -name '.DS_Store' -exec rm -fr {} +

.PHONY: clean-test
clean-test:
	rm -fr .tox/
	rm -f .coverage
	find . -name ".coverage*" -not -name ".coveragerc" -exec rm -fr "{}" \;
	rm -fr coverage.xml
	rm -fr htmlcov/
	rm -fr .hypothesis
	rm -fr .pytest_cache
	rm -fr .mypy_cache/
	rm -fr .hypothesis/
	find . -name 'log.txt' -exec rm -fr {} +
	find . -name 'log.*.txt' -exec rm -fr {} +

# isort: fix import orders
# black: format files according to the pep standards
.PHONY: formatters
formatters:
	tomte format-code

# black-check: check code style
# isort-check: check for import order
# flake8: wrapper around various code checks, https://flake8.pycqa.org/en/latest/user/error-codes.html
# mypy: static type checker
# pylint: code analysis for code smells and refactoring suggestions
# darglint: docstring linter
.PHONY: code-checks
code-checks:
	tomte check-code

# safety: checks dependencies for known security vulnerabilities
# bandit: security linter
.PHONY: security
security:
	tomte check-security
	gitleaks detect --report-format json --report-path leak_report

# generate latest hashes for updated packages
# generate docs for updated packages
# update copyright headers
.PHONY: generators
generators:
	tox -e abci-docstrings
	tomte format-copyright --author author_name
	autonomy packages lock

.PHONY: common-checks-1
common-checks-1:
	tomte check-copyright --author author_name
	tomte check-doc-links --url-skips https://soft-sly-slug.base-mainnet.quiknode.pro/f13d998d9d68685faeee903499e15b4b386a8b1c/
	tox -p -e check-hash -e check-packages -e check-doc-hashes

.PHONY: fix-abci-app-specs
fix-abci-app-specs:
	export PYTHONPATH=${PYTHONPATH}:${PWD}
	autonomy analyse fsm-specs --update --app-class MemeooorrAbciApp --package packages/dvilela/skills/memeooorr_abci/ || (echo "Failed to check memeooorr_abci abci consistency" && exit 1)
	autonomy analyse fsm-specs --update --app-class MemeooorrChainedSkillAbciApp --package packages/dvilela/skills/memeooorr_chained_abci/ || (echo "Failed to check memeooorr_chained_abci abci consistency" && exit 1)

.PHONY: tm
tm:
	rm -r ~/.tendermint
	tendermint init
	tendermint node --proxy_app=tcp://127.0.0.1:26658 --rpc.laddr=tcp://127.0.0.1:26657 --p2p.laddr=tcp://0.0.0.0:26656 --p2p.seeds= --consensus.create_empty_blocks=true

.PHONY: all-linters
all-linters:
	gitleaks detect --report-format json --report-path leak_report
	tox -e spell-check
	tox -e liccheck
	tox -e check-doc-hashes
	tox -e bandit
	tox -e safety
	tox -e check-packages
	tox -e check-abciapp-specs
	tox -e check-hash
	tox -e black-check
	tox -e isort-check
	tox -e flake8
	tox -e darglint
	tox -e pylint
	tox -e mypy

.PHONY: push-image
push-image:
	@AGENT_HASH=$$(jq -r ".dev[\"agent/dvilela/memeooorr/0.1.0\"]" packages/packages.json) && \
	SERVICE_HASH=$$(jq -r ".dev[\"service/dvilela/memeooorr/0.1.0\"]" packages/packages.json) && \
	IMAGE_ID=$$(docker image ls | awk -v tag="$$AGENT_HASH" '$$2 == tag {print $$3}' | head -n 1) && \
	echo "Tagging image $$IMAGE_ID -> dvilela/oar-memeooorr:$$AGENT_HASH" && \
	docker tag $$IMAGE_ID dvilela/oar-memeooorr:$$AGENT_HASH && \
	docker push dvilela/oar-memeooorr:$$AGENT_HASH

.PHONY: push-packages
push-packages:
	make clean  && \
	autonomy push-all

.PHONY: publish
publish:
	make push-packages  && \
	bash build_image.sh && \
	make push-image

.PHONY: deploy-contracts
deploy-contracts:
	npx hardhat run scripts/deployment/deploy_01_meme_base.js --network base

.PHONY: bump-packages
bump-packages:
	@AUTONOMY_VERSION=$$(poetry show open-autonomy | grep version | cut -d':' -f2 | xargs) && \
	AEA_VERSION=$$(poetry show open-aea | grep version | cut -d':' -f2 | xargs) && \
	echo "Bumping packages to open-autonomy $${AUTONOMY_VERSION}" && \
	echo "Bumping packages to open-aea $${AEA_VERSION}" && \
	autonomy packages sync --source valory-xyz/open-autonomy:v$${AUTONOMY_VERSION} --source valory-xyz/open-aea:v$${AEA_VERSION} --update-packages

.PHONY: run-agent
run-agent:
	bash run_agent.sh 2>&1 | tee agent_log.log
.PHONY: gitleaks-ignore
gitleaks-ignore:
	python scripts/gitleaks_ignore.py

v := $(shell pip -V | grep virtualenvs)
