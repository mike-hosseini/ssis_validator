# ssis_validator

A Python package for validating SQL Server Integration Services (SSIS) projects. It can be used as a part of Continuous Integration pipeline.

This Python application is written for Python 3.7+.

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

1. Project Server Version
2. Project Protection Level
3. Packages Presence in Project
4. Correct Linkage of Packages
5. Project Deployment Model

### Package

1. Package Last Modified Visual Studio Version
2. Package Protection Level
3. (Optional) PragmaticWorks BIxPress Presence
4. (Optional) PragmaticWorks BIxPress Continue Execution on Error
5. (Optional) PragmaticWorks BIxPress No Reporting of Error on Failure

## Contribution

See an area for improvement, please open an issue or send a PR. :-)

## Future Improvements

- [ ] mypy type hints
- [ ] add configuration file
