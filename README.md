# ssis_validator

A Python package for validating SQL Server Integration Services (SSIS) projects. It can be used as a part of Continuous Integration pipeline.

The module works by parsing the XML content of SSIS Projects and Packages while handling all the rough edges. It identifies the configurations of the projects and validates whether they meet the specifications.

This Python application is written for Python 3.7+.

## Install

This package is available on [PyPi](https://pypi.org/project/ssis-validator/) package repository. You can install it like below:

```bash
pip install ssis_validator
```

## Usage

### 1. Projects

Specify one or multiple `--project` arguments and provide the full path to the SSIS Projects that you want to validate.

```bash
ssis_validator --project Project_1 --project Project_2
```

### 2. Repository Staging

Specify `--repository` optional argument along with one `--project` argument passing the Git repository hosting multiple SSIS Projects. The validator only checks SSIS projects that are staged.


```bash
ssis_validator --project Project_1 --repository
```

## Validation Criteria

The following validation criteria are currently checked. The current version has the accepted specifications hard-coded. The next version will parameterize all of them in a configuration file.

### Project

1. Project Server Version: `SQLServer2014`, `SQLServer2016`
2. Project Protection Level: `EncryptSensitiveWithPassword`
3. Packages Presence in Project: `True`
4. Linkage of Packages: `True`
5. Project Deployment Model: `Project`

### Package

1. Package Last Modified Visual Studio Version: `SSIS_2016`
2. Package Protection Level: `EncryptSensitiveWithPassword`
3. (Optional) PragmaticWorks BIxPress Server Name: `server_name`
4. (Optional) PragmaticWorks BIxPress Continue Execution on Error: `True`
5. (Optional) PragmaticWorks BIxPress Reporting of Error on Failure: `False`

## Contribution

See an area for improvement, please open an issue or send a PR.

## Future Improvements

- [ ] mypy type hints
- [ ] add configuration file
