# ENV defaults to local (so that requirements/local.txt are installed), but can be overridden
#  (e.g. ENV=production make setup).
ENV ?= local
# PYTHON specifies the python binary to use when creating virtualenv
PYTHON ?= python3.9

# Editor can be defined globally but defaults to nano
EDITOR ?= nano

# By default we open the editor after copying settings, but can be overridden
#  (e.g. EDIT_SETTINGS=no make settings).
EDIT_SETTINGS ?= yes

# Get root dir and project dir
PROJECT_ROOT ?= $(PWD)
SITE_ROOT ?= $(PROJECT_ROOT)

BLACK ?= \033[0;30m
RED ?= \033[0;31m
GREEN ?= \033[0;32m
YELLOW ?= \033[0;33m
BLUE ?= \033[0;34m
PURPLE ?= \033[0;35m
CYAN ?= \033[0;36m
GRAY ?= \033[0;37m
COFF ?= \033[0m

.PHONY: all help setup pycharm coverage test clean
.PHONY: isort isort-fix quality flake8


all: help


help:
	@echo "+------<<<<                                 Configuration                                >>>>------+"
	@echo ""
	@echo "ENV: $(ENV)"
	@echo "PYTHON: $(PYTHON)"
	@echo "PROJECT_ROOT: $(PROJECT_ROOT)"
	@echo "SITE_ROOT: $(SITE_ROOT)"
	@echo ""
	@echo "+------<<<<                                     Tasks                                    >>>>------+"
	@echo ""
	@echo "$(CYAN)make pycharm$(COFF)  - Copies default PyCharm settings (unless they already exist)"
	@echo ""
	@echo "$(CYAN)make test$(COFF)     - Runs automatic tests on your python code"
	@echo ""
	@echo "$(CYAN)make coverage$(COFF) - Runs code test coverage calculation"
	@echo ""
	@echo "$(CYAN)make quality$(COFF)  - Runs automatic code quality tests on your code"
	@echo ""



pycharm: $(PROJECT_ROOT)/.idea


$(PROJECT_ROOT)/.idea:
	@echo "$(CYAN)Creating pycharm settings from template$(COFF)"
	@mkdir -p $(PROJECT_ROOT)/.idea && cp -R $(PROJECT_ROOT)/.idea_template/* $(PROJECT_ROOT)/.idea/


settings: $(PROJECT_ROOT)/.env


coverage:
	@echo "$(CYAN)Running automatic code coverage check$(COFF)"
	@coverage run -m py.test
	@coverage html
	@coverage report

pre-commit:
	@echo "$(CYAN)Running pre-commit routine$(COFF)"
	pipenv run pre-commit run --all-files
	make flake8

test: clean
	@echo "$(CYAN)Running automatic tests$(COFF)"
	@py.test --disable-warnings


clean:
	@echo "$(CYAN)Cleaning pyc files$(COFF)"
	@cd $(SITE_ROOT) && find . -name "*.pyc" -exec rm -rf {} \;


isort:
	@echo "$(CYAN)Checking imports with isort$(COFF)"
	isort --recursive --check-only -p . --diff


isort-fix:
	@echo "$(CYAN)Fixing imports with isort$(COFF)"
	isort --recursive -p .


quality: flake8 isort


flake8:
	@echo "$(CYAN)Running flake8$(COFF)"
	@flake8


docker-django:
	$(cmd)
