import pathlib

import lxml.etree
import pytest

import ssis_validator


def dtsx_file(protection_level, last_mod_prod_ver, conn_name, conn_server):
    # DTS Executable
    def dts(
        prop, nsmap={"DTS": "www.microsoft.com/SqlServer/Dts"}, ns_name="DTS"
    ):
        return f"{{{nsmap[ns_name]}}}{prop}"

    ssis_project = lxml.etree.Element(
        dts("Executable"),
        attrib={
            dts("ProtectionLevel"): protection_level,
            dts("LastModifiedProductVersion"): last_mod_prod_ver,
        },
        nsmap={"DTS": "www.microsoft.com/SqlServer/Dts"},
    )

    # Connection Managers
    connection_managers = lxml.etree.SubElement(
        ssis_project, dts("ConnectionManagers")
    )
    connection_manager = lxml.etree.SubElement(
        connection_managers,
        dts("ConnectionManager"),
        attrib={dts("DelayValidation"): "True", dts("ObjectName"): conn_name},
    )
    object_data = lxml.etree.SubElement(connection_manager, dts("ObjectData"))
    lxml.etree.SubElement(
        object_data,
        dts("ConnectionManager"),
        attrib={
            dts("ConnectionString"): ";".join(
                (f"Data Source={conn_server}", "Initial Catalog=BIxPress;")
            )
        },
    )

    # Event Handlers
    event_handlers = lxml.etree.SubElement(ssis_project, dts("EventHandlers"))
    event_handler = lxml.etree.SubElement(event_handlers, dts("EventHandler"))
    exectuables = lxml.etree.SubElement(event_handler, dts("Executables"))
    lxml.etree.SubElement(
        exectuables,
        dts("Executable"),
        attrib={
            dts("ForceExecutionResult"): "0",
            dts("ObjectName"): "SSISOpsEhObj_Package_OnError",
        },
    )

    return lxml.etree.tostring(
        ssis_project, xml_declaration=True, encoding="utf-8", pretty_print=True
    )


def dtproj_file(protection_level, package_name, target_server_version):
    project = lxml.etree.Element(
        "Project",
        nsmap={
            "xsd": "http://www.w3.org/2001/XMLSchema",
            "xsi": "http://www.w3.org/2001/XMLSchema-instance",
        },
    )

    deployment_model = lxml.etree.SubElement(project, "DeploymentModel")
    deployment_model.text = "Project"

    product_version = lxml.etree.SubElement(project, "ProductVersion")
    product_version.text = "14.0.1000.169"

    deployment_model_specific_content = lxml.etree.SubElement(
        project, "DeploymentModelSpecificContent"
    )

    # Manifest
    manifest = lxml.etree.SubElement(
        deployment_model_specific_content, "Manifest"
    )
    nsmap = {"SSIS": "www.microsoft.com/SqlServer/SSIS"}

    def ssis(
        prop, nsmap={"SSIS": "www.microsoft.com/SqlServer/SSIS"}, ns_name="SSIS"
    ):
        return f"{{{nsmap[ns_name]}}}{prop}"

    ssis_project = lxml.etree.Element(
        ssis("Project"),
        attrib={ssis("ProtectionLevel"): protection_level},
        nsmap=nsmap,
    )
    manifest.append(ssis_project)

    # SSIS Packages
    ssis_packages = lxml.etree.SubElement(ssis_project, ssis("Packages"))
    lxml.etree.SubElement(
        ssis_packages,
        ssis("Package"),
        attrib={ssis("Name"): package_name, ssis("EntryPoint"): "1"},
    )

    # Configurations
    configurations = lxml.etree.SubElement(project, "Configurations")
    configuration = lxml.etree.SubElement(configurations, "Configuration")
    configuration_name = lxml.etree.SubElement(configuration, "Name")
    configuration_name.text = "Development"
    configuration_options = lxml.etree.SubElement(configuration, "Options")
    configuration_output_path = lxml.etree.SubElement(
        configuration_options, "OutputPath"
    )
    configuration_output_path.text = "bin"
    configuration_target_server_version = lxml.etree.SubElement(
        configuration_options, "TargetServerVersion"
    )
    configuration_target_server_version.text = target_server_version

    return lxml.etree.tostring(
        project, xml_declaration=True, encoding="utf-8", pretty_print=True
    )


@pytest.fixture
def dtproj_file_1(tmpdir):
    project_dtproj = tmpdir.mkdir("ssis_project").join("Project.dtproj")
    project_dtproj.write(
        dtproj_file("DontSaveSensitive", "Package.dtsx", "SQLServer2014")
    )

    return project_dtproj


def test_dtproj_parsing_incorrectly_linked(tmpdir, dtproj_file_1):
    dtproj_path = pathlib.Path(tmpdir) / dtproj_file_1
    dtproj = ssis_validator.SSISProject(dtproj_path.stem, dtproj_path)

    ssis_project = ssis_validator.ValidationPipeline._parse_dtproj_file(dtproj)

    dtsx_path = pathlib.Path(tmpdir) / "ssis_project" / "Package.dtsx"
    ssis_packages = [ssis_validator.SSISPackage(dtsx_path.name, dtsx_path)]

    assert ssis_project.name == dtproj_path.stem
    assert ssis_project.path == dtproj_path
    assert ssis_project.packages == ssis_packages
    assert ssis_project.incorrectly_linked == True
    assert ssis_project.target_server_version == "SQLServer2014"
    assert ssis_project.protection_level == "DontSaveSensitive"


@pytest.fixture
def dtsx_file_1(tmpdir):
    dtsx = tmpdir.mkdir("ssis_project_2").join("Package.dtsx")
    test = dtsx_file("2", "14.0.3008.28", "OLEDB_BIxPress_1", "server_name")
    dtsx.write(test)

    return dtsx


def test_dtsx_parsing(tmpdir, dtsx_file_1):
    dtsx_path = pathlib.Path(tmpdir) / dtsx_file_1
    ssis_package = ssis_validator.SSISPackage(dtsx_path.stem, dtsx_path)
    dtsx = ssis_validator.ValidationPipeline._parse_dtsx_file(ssis_package)

    assert dtsx.name == dtsx_path.stem
    assert dtsx.path == dtsx_path
    assert dtsx.last_modified_version == 14
    assert dtsx.protection_level == 2
    assert "server_name" in dtsx.bix_con_name
    assert dtsx.bix_option_continue_exec == "True"
    assert dtsx.bix_option_no_report_fail == "0"
