__version__ = "0.1.0"

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, List, Optional, Union

import colorama
import crayons
import git
from lxml import etree

colorama.init()

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(lineno)d:%(name)s: %(message)s",
    level=logging.DEBUG,
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)

logger = logging.getLogger("validator")

for module in "git.cmd", "git.util", "matplotlib":
    logging.getLogger(module).disabled = True


class SSISProject:
    def __init__(
        self,
        name,
        path,
        packages=[],
        incorrectly_linked=False,
        target_server_version=None,
        protection_level=None,
        deployment_model=None,
    ):
        self.name = name
        self.path = path
        self.packages = packages
        self.incorrectly_linked = incorrectly_linked
        self.target_server_version = target_server_version
        self.protection_level = protection_level
        self.deployment_model = deployment_model


class SSISPackage:
    def __init__(
        self,
        name,
        path,
        last_modified_version=None,
        protection_level=None,
        bix_con_name=None,
        bix_option_continue_exec=None,
        bix_option_no_report_fail=None,
    ):
        self.name = name
        self.path = path
        self.last_modified_version = last_modified_version
        self.protection_level = protection_level
        self.bix_con_name = bix_con_name
        self.bix_option_continue_exec = bix_option_continue_exec
        self.bix_option_no_report_fail = bix_option_no_report_fail

    def __eq__(self, other):
        if isinstance(self, other.__class__):
            return self.name == other.name and self.path == other.path
        return False

    def __repr__(self):
        return f"SSISPackage({self.name})"


class Validation:
    def __init__(self, successful=False, message=None):
        self.successful = successful
        self.message = message

    def __str__(self):
        color = crayons.green if self.successful else crayons.red
        return str(color(self.message))


class ValidationResult:
    def __init__(self, name, path, result):
        self.name = name
        self.path = path
        self.result = result


class Mode:
    def __init__(
        self, name: str, directories: List[Path], is_repo: bool
    ) -> None:
        self.name = name
        self.directories = directories
        self.is_repo = is_repo


class CIException(Exception):
    def __init__(self, message: str) -> None:
        super(CIException, self).__init__(message)


class ValidationException(CIException):
    def __init__(self, message: str, object_name: str) -> None:
        super(ValidationException, self).__init__(
            f"{object_name} - failed validating: {message}"
        )


class ValidationPipeline:

    PACKAGE_VERSIONS = {
        11: "SSIS_2012",
        12: "SSIS_2014",
        13: "SSIS_2016",
        14: "SSIS_2017",
        15: "SSIS_2019",
        0: "unknown",
        None: "unknown",
    }

    PACKAGE_ENCRYPTIONS = {
        0: "DontSaveSensitive",
        1: "EncryptSensitiveWithUserKey",
        2: "EncryptSensitiveWithPassword",
        3: "EncryptAllWithPassword",
        4: "EncryptAllWithUserKey",
        None: "unknown",
    }

    PROJECT_VERSIONS = {"SQLServer2014": 12, "SQLServer2016": 13}
    ALLOWED_ENCRYPTION_METHOD = "EncryptSensitiveWithPassword"
    BIXPRESS_SERVER_NAME = "server_name"
    BIXPRESS_CONNECTION_NAME = "OLEDB_BIxPress_1"
    ERROR_EVENT_NAME = "SSISOpsEhObj_Package_OnError"

    def __init__(self, mode: Mode) -> None:
        self.mode: Mode = mode
        self.validated_projects: List[Any] = []

    def run(self) -> None:
        try:
            changed_projects = (
                self._get_repo_changes(self.mode.directories[0])
                if self.mode.is_repo
                else self._get_dir_dtproj_files(self.mode.directories)
            )

            projects = self._get_ssis_projects(changed_projects)
            parsed_projects = self._process_dtproj_files(projects)
            self.validated_projects = self.validate_projects(parsed_projects)
        except:
            raise

    def _get_dir_dtproj_files(self, directories: List[Path]) -> List[Path]:
        projects = []
        for directory in directories:
            if not directory.exists():
                raise CIException(f"Invalid folder specified: {directory}")
            for dtproj in directory.rglob("*.dtproj"):
                projects.append(dtproj)
        return projects

    def _get_repo_changes(self, current_directory: Path) -> List[Path]:
        if not (current_directory / ".git").exists():
            raise CIException(
                "No repository found, navigate inside a repository "
                "with multiple SSIS project directories present"
            )

        return [
            current_directory / Path(x.a_path)
            for x in git.Repo(current_directory).index.diff("HEAD")
            if Path(x.a_path).suffix == ".dtproj"
        ]

    def _get_ssis_projects(self, projects: List[Path]) -> List[SSISProject]:
        dtproj_files = [SSISProject(dtproj.stem, dtproj) for dtproj in projects]

        if not dtproj_files:
            raise CIException(
                "No .dtproj files were found in the supplied folder"
            )

        return dtproj_files

    @staticmethod
    def _parse_dtsx_protection(xpath):
        try:
            protection_level = None if not xpath else int(xpath[0])
            protection_level = (
                protection_level if protection_level is not None else 1
            )
        except TypeError:
            return 0

        return protection_level

    @staticmethod
    def _parse_dtsx_modified_version(xpath):
        try:
            last_modified_version = (
                None if not xpath else int(xpath[0].split(".")[0])
            )
        except TypeError:
            return 0

        return last_modified_version

    @staticmethod
    def _read_xml_file(path, encoding):
        try:
            with path.open("r", encoding=encoding) as f:
                parsed_xml = etree.fromstring(f.read())
        except ValueError:
            with path.open("rb") as f:
                parsed_xml = etree.fromstring(f.read())
        except FileNotFoundError:
            parsed_xml = ""

        return parsed_xml

    @staticmethod
    def _parse_dtproj_file(dtproj: SSISProject) -> SSISProject:
        parsed_xml = ValidationPipeline._read_xml_file(dtproj.path, "utf-8")

        if not parsed_xml:
            raise FileNotFoundError("No DTPROJ file was found")

        ssis_namespace = {"SSIS": "www.microsoft.com/SqlServer/SSIS"}

        # SSISProject.target_server_version
        deployment_version = parsed_xml.xpath(
            "/".join(
                [
                    "//Configurations",
                    "Configuration",
                    "Options",
                    "TargetServerVersion",
                ]
            ),
            namespaces=parsed_xml.nsmap,
        )
        dtproj_target_server_version = (
            None if not deployment_version else deployment_version[0].text
        )

        # SSISProject.product_version
        # product_version = parsed_xml.xpath("//ProductVersion")
        # dtproj_product_version = (
        #     None
        #     if not product_version
        #     else product_version[0].text.split(".")[0]
        # )

        # SSISProject.deployment_model
        deployment_model = parsed_xml.xpath("//DeploymentModel")
        dtproj_deployment_model = (
            None if not deployment_model else deployment_model[0].text
        )

        # SSISProject.protection_level
        protection_level_tree = parsed_xml.xpath(
            "/".join(
                [
                    "//DeploymentModelSpecificContent",
                    "Manifest",
                    "SSIS:Project",
                    "@SSIS:ProtectionLevel",
                ]
            ),
            namespaces=ssis_namespace,
        )
        dtproj_protection_level = (
            None if not protection_level_tree else protection_level_tree[0]
        )

        # SSISProject.packages
        dtproj_packages = [
            SSISPackage(Path(dtsx).name, dtproj.path.parent / Path(dtsx))
            for dtsx in parsed_xml.xpath(
                "/".join(
                    [
                        "//DeploymentModelSpecificContent",
                        "Manifest",
                        "SSIS:Project",
                        "SSIS:Packages",
                        "SSIS:Package",
                        "@SSIS:Name",
                    ]
                ),
                namespaces=ssis_namespace,
            )
        ]

        dtproj_incorrectly_linked = any(
            not dtsx.path.is_file() for dtsx in dtproj_packages
        )

        return SSISProject(
            dtproj.name,
            dtproj.path,
            dtproj_packages,
            dtproj_incorrectly_linked,
            dtproj_target_server_version,
            dtproj_protection_level,
            dtproj_deployment_model,
        )

    def _process_dtproj_files(
        self, projects: List[SSISProject]
    ) -> List[SSISProject]:
        parsed_projects = []
        for dtproj in projects:
            logger.info(f"o  Processing: {dtproj.name}")
            try:
                parsed_projects.append(self._parse_dtproj_file(dtproj))
            except:
                raise
        self._process_dtsx_files(parsed_projects)
        return parsed_projects

    @staticmethod
    def _parse_dtsx_file(package: SSISPackage) -> SSISPackage:
        try:
            parsed_xml = ValidationPipeline._read_xml_file(
                package.path, "utf-8-sig"
            )

            if not len(parsed_xml):
                return package

            xml_namespace = parsed_xml.nsmap

            # SSISPackage.protection_level
            package.protection_level = ValidationPipeline._parse_dtsx_protection(
                parsed_xml.xpath(
                    "//DTS:Executable/@DTS:ProtectionLevel",
                    namespaces=xml_namespace,
                )
            )

            # SSISPackage.last_modified_version
            package.last_modified_version = ValidationPipeline._parse_dtsx_modified_version(
                parsed_xml.xpath(
                    f"//DTS:Executable/@DTS:LastModifiedProductVersion",
                    namespaces=xml_namespace,
                )
            )

            # SSISPackage.bix_con_name
            bixpress_conn_xpath = parsed_xml.xpath(
                "/".join(
                    [
                        "//DTS:ConnectionManager[@DTS:ObjectName='{}']".format(
                            ValidationPipeline.BIXPRESS_CONNECTION_NAME
                        ),
                        "DTS:ObjectData",
                        "DTS:ConnectionManager",
                        "@DTS:ConnectionString",
                    ]
                ),
                namespaces=xml_namespace,
            )
            package.bix_con_name = (
                None if not bixpress_conn_xpath else bixpress_conn_xpath[0]
            )

            # SSISPackage.bix_option_continue_exec
            bixpress_delay_validation_xpath = parsed_xml.xpath(
                "/".join(
                    [
                        "//DTS:ConnectionManager[@DTS:ObjectName='{}']".format(
                            ValidationPipeline.BIXPRESS_CONNECTION_NAME
                        ),
                        "@DTS:DelayValidation",
                    ]
                ),
                namespaces=xml_namespace,
            )
            package.bix_option_continue_exec = (
                None
                if not bixpress_delay_validation_xpath
                else bixpress_delay_validation_xpath[0]
            )

            # SSISPackage.bix_option_no_report_fail
            bixpress_onerror_xpath = parsed_xml.xpath(
                "/".join(
                    [
                        "//DTS:Executable[@DTS:ObjectName='{}']".format(
                            ValidationPipeline.ERROR_EVENT_NAME
                        ),
                        "@DTS:ForceExecutionResult",
                    ]
                ),
                namespaces=xml_namespace,
            )
            package.bix_option_no_report_fail = (
                None
                if not bixpress_onerror_xpath
                else bixpress_onerror_xpath[0]
            )
        except TypeError:
            if etree.SubElement(parsed_xml, "EncryptedData") is not None:
                package.protection_level = 3

        return SSISPackage(
            package.name,
            package.path,
            package.last_modified_version,
            package.protection_level,
            package.bix_con_name,
            package.bix_option_continue_exec,
            package.bix_option_no_report_fail,
        )

    def _process_dtsx_files(self, projects: List[SSISProject]) -> None:
        for dtproj in projects:
            packages = []
            for package in dtproj.packages:
                packages.append(ValidationPipeline._parse_dtsx_file(package))
            dtproj.packages = packages

    def validate_dtproj_server_version(
        self, project: SSISProject
    ) -> Validation:
        validation = Validation()
        if not project.target_server_version:
            validation.successful = False
            validation.message = (
                f"- {project.path.name} - failed validating: "
                + "the project does not have a deployment configuration"
                + " likely because the project is built for SQL Server 2012"
            )

        elif (
            project.target_server_version
            not in ValidationPipeline.PROJECT_VERSIONS
        ):
            validation.successful = False
            validation.message = "- {} - failed validating: the project version should be {},".format(
                project.path.name,
                " or ".join(ValidationPipeline.PROJECT_VERSIONS),
            ) + " but your current version is {}".format(
                project.target_server_version
            )
        else:
            validation.successful = True
            validation.message = "+ {} - successfully validated:".format(
                project.path.name
            ) + " Target Server Version: {}".format(
                project.target_server_version
            )

        return validation

    def validate_dtproj_protection_level(
        self, project: SSISProject
    ) -> Validation:
        validation = Validation()
        if (
            not project.protection_level
            or project.protection_level
            != ValidationPipeline.ALLOWED_ENCRYPTION_METHOD
        ):
            validation.successful = False
            validation.message = "- {} - failed validating: the project protection level should be {} but yours is {}".format(
                project.path.name,
                ValidationPipeline.ALLOWED_ENCRYPTION_METHOD,
                project.protection_level,
            )
        else:
            validation.successful = True
            validation.message = "+ {} - successfully validated: Project Protection Level: {}".format(
                project.path.name, project.protection_level
            )
        return validation

    def validate_dtproj_packages(self, project: SSISProject) -> Validation:
        validation = Validation()
        if not project.packages:
            validation.successful = False
            validation.message = f"- {project.path.name} - failed validating: no linked packages found"

        validation.successful = True
        validation.message = f"+ {project.path.name} - successfully validated: linked packages are present"
        return validation

    def validate_dtproj_package_linking(
        self, project: SSISProject
    ) -> Validation:
        validation = Validation()
        if project.incorrectly_linked:
            validation.successful = False
            validation.message = "- {} - failed validating: the packages in the project are not properly linked".format(
                project.path.name
            )

        validation.successful = True
        validation.message = f"+ {project.path.name} - successfully validated: correct linking of packages"

        return validation

    def validate_deployment_model(self, project: SSISProject) -> Validation:
        validation = Validation()
        if project.deployment_model is None:
            validation.successful = False
            validation.message = f"+ {project.path.name} - failed validating: no deployment model found"
        elif project.deployment_model == "Package":
            validation.successful = False
            validation.message = f"+ {project.path.name} - failed validating: deployment model should be Project not Package"
        elif project.deployment_model == "Project":
            validation.successful = True
            validation.message = f"+ {project.path.name} - successfully validated: Deployment Model: Project"

        return validation

    def validate_dtsx_version(self, package: SSISPackage) -> Validation:
        validation = Validation()
        if (
            package.last_modified_version is None
            and package.last_modified_version not in [12, 13, 14]
        ):
            validation.successful = False
            validation.message = "- {} - failed validating: the package version should be {}, but your current version is {}".format(
                package.name,
                ValidationPipeline.PACKAGE_VERSIONS[13],
                ValidationPipeline.PACKAGE_VERSIONS.get(
                    package.last_modified_version, None
                ),
            )
        else:
            validation.successful = True
            validation.message = "+ {} - successfully validated: Last Modified Product Version".format(
                package.name
            )

        return validation

    def validate_dtsx_protection(self, package: SSISPackage) -> Validation:
        validation = Validation()
        if package.protection_level is None or package.protection_level != 2:
            validation.successful = False
            validation.message = "- {} - failed validating: the package protection level should be {}".format(
                package.name, ValidationPipeline.ALLOWED_ENCRYPTION_METHOD
            )
        else:
            validation.successful = True
            validation.message = "+ {} - successfully validated: Package Protection Level".format(
                package.name
            )
        return validation

    def validate_dtsx_bix_con(self, package: SSISPackage) -> Validation:
        validation = Validation()

        if not package.bix_con_name:
            validation.successful = False
            validation.message = "- {} - failed validating: BIxPress Auditing Framework is missing, make sure it is present with {} connection name".format(
                package.name, ValidationPipeline.BIXPRESS_CONNECTION_NAME
            )
        elif (
            ValidationPipeline.BIXPRESS_SERVER_NAME
            not in package.bix_con_name.lower()
        ):
            validation.successful = False
            validation.message = "- {} - failed validating: the server name for BIxPress Auditing Framework should be {}".format(
                package.name, ValidationPipeline.BIXPRESS_SERVER_NAME
            )
        else:
            validation.successful = True
            validation.message = "+ {} - successfully validated: presence of BIxPress Auditing Framework".format(
                package.name
            )

        return validation

    def validate_dtsx_bix_continue_option(
        self, package: SSISPackage
    ) -> Validation:
        validation = Validation()

        if not package.bix_option_continue_exec:
            validation.successful = False
            validation.message = (
                "- {} - failed validating: the following checkbox was not checked on BIxPress:".format(
                    package.name
                )
                + " Continue package execution on Auditing Framework database connection failure"
            )
        else:
            validation.successful = True
            validation.message = "+ {} - successfully validated: BIxPress continue execution option".format(
                package.name
            )
        return validation

    def validate_dtsx_bix_error_reporting(
        self, package: SSISPackage
    ) -> Validation:
        validation = Validation()
        if (
            package.bix_option_no_report_fail is None
            or package.bix_option_no_report_fail != "0"
        ):
            validation.successful = False
            validation.message = "- {} - failed validating: the following checkbox was not checked on BIxPress: Do not report failure if Auditing Framework fails".format(
                package.name
            )
        else:
            validation.successful = True
            validation.message = "+ {} - successfully validated: BIxPress 'do not report failure' option".format(
                package.name
            )
        return validation

    def validate_projects(self, projects: List[SSISProject]) -> List[Any]:
        all_validations: List[object] = []

        for project in projects:
            project_validation = ValidationResult(
                project.name,
                project.path,
                [
                    self.validate_dtproj_server_version(project),
                    self.validate_dtproj_protection_level(project),
                    self.validate_dtproj_packages(project),
                    self.validate_dtproj_package_linking(project),
                    self.validate_deployment_model(project),
                ],
            )

            packages_validation = []
            if not project.incorrectly_linked:
                for package in project.packages:
                    packages_validation.append(
                        ValidationResult(
                            package.name,
                            package.path,
                            [
                                self.validate_dtsx_version(package),
                                self.validate_dtsx_protection(package),
                                self.validate_dtsx_bix_con(package),
                                self.validate_dtsx_bix_continue_option(package),
                                self.validate_dtsx_bix_error_reporting(package),
                            ],
                        )
                    )

            all_validations.append([project_validation, packages_validation])

        return all_validations

    def print_validation_result(self) -> None:
        print()
        project_validation_successful = True
        for project, packages in self.validated_projects:
            print("-" * 80 + "\n")
            logger.info(crayons.cyan(f"o  Validating {project.name}"))
            print()
            logger.info(f"o  Validating {project.path}")
            print()

            for result in sorted(
                project.result, key=lambda x: not x.successful
            ):
                print(result)

                if not result.successful:
                    project_validation_successful = False

            if project.result:
                print()

            packages_validation_successful = True
            for package in packages:
                logger.info(f"o  Validating {package.path}")
                print()
                for result in sorted(
                    package.result, key=lambda x: not x.successful
                ):
                    print(result)
                    if not result.successful:
                        packages_validation_successful = False

            if packages:
                print()

            if packages_validation_successful and project_validation_successful:
                logger.info(
                    crayons.cyan(f"o  Successfully validated: {project.name}")
                )
            else:
                logger.info(
                    crayons.cyan(f"o  Failed validating: {project.name}")
                )

            print()

        print("-" * 80)


def determine_mode(args: List[str]) -> Mode:
    mode = None
    if args.repository and args.repository is not None:
        mode = Mode("Repository", [Path(args.projects[0])], True)
    elif args.projects is not None:
        mode = Mode("Directory", [Path(p) for p in args.projects], False)
    else:
        raise ValueError("Invalid argument provided")

    return mode


def print_mode_info(mode: Mode) -> None:
    print()
    if mode.is_repo:
        logger.info("o  Mode: Repository")
        logger.info(f"o  Looking for staged projects in {mode.directories[0]}")
    else:
        logger.info("o  Mode: Directory")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ssis_validator",
        description="Validates SSIS Package XML file to ensure consistent"
        "configuration per predefined specifications",
    )

    parser.add_argument(
        "-r",
        "--repository",
        action="store_true",
        help="Flag for whether validating staging of a Git repository",
    )

    parser.add_argument(
        "-p",
        "--projects",
        action="append",
        required=True,
        help="Path to SSIS Projects",
        metavar="PROJECT_NAME",
    )

    args = parser.parse_args()

    mode = determine_mode(args)
    print_mode_info(mode)

    try:
        validation_pipeline = ValidationPipeline(mode)
        validation_pipeline.run()
        validation_pipeline.print_validation_result()
    except Exception as e:
        print()
        logger.exception(crayons.red(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
