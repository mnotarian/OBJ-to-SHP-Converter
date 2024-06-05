"""
Model exported as python.
Name : Convert 3D OBJ to 3D SHP Polygon
Group : TARP
With QGIS : 33601
"""
#This version works with relative paths on Windows, MacOSX or Linux systems
#A folder is created in the user directory with another python script and to store temporary shapefiles
#Blender must also be installed on the system
#The Blender-GIS Addon must also be installed inside Blender
#The Blender.exe file will be found in the Program Files (Windows) or Applications (MacOS) directory
#If installed in another location, script might fail
#Warning - MacOSX and Linux functionality is untested!

from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterNumber
from qgis.core import QgsProcessingParameterFile
from qgis.core import QgsCoordinateReferenceSystem
import processing
import subprocess
import platform
from pathlib import Path
import math

class Convert3dOBJTo3dSHPPolygon(QgsProcessingAlgorithm):
    
    #default values for output path, year, SU can be adjusted here
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile('obj_file', 'OBJ File', behavior=QgsProcessingParameterFile.File, fileFilter='OBJ Files (*.obj)', defaultValue=None))
        self.addParameter(QgsProcessingParameterFile('output_file_path', 'Output File Path', behavior=QgsProcessingParameterFile.Folder, fileFilter='All files (*.*)', defaultValue='C:\\SynologyDrive\\GIS_2023\\3D_SU_Shapefiles'))
        self.addParameter(QgsProcessingParameterNumber('su_number', 'SU Number', type=QgsProcessingParameterNumber.Integer, defaultValue=None))
        self.addParameter(QgsProcessingParameterNumber('year', 'Year', type=QgsProcessingParameterNumber.Integer, defaultValue=2024))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(10, model_feedback)
        results = {}
        outputs = {}
        root = Path.home().parent.parent

        #Create output path objects for interoperability - create filenames and paths
        new_output_path = Path(parameters ['output_file_path'])
        print("new output path: ", new_output_path)
        local_filename = 'SU_' + str(parameters['su_number']) + '_LC.shp'
        global_filename = 'SU_' + str(parameters['su_number']) + '_EPSG_32632.shp'
        local_path = Path.joinpath(new_output_path, local_filename)
        print("local path: ", local_path)
        global_path = Path.joinpath(new_output_path, global_filename)
        print("global path: ", global_path)

        #Locates the path of Blender application executable
        if platform.system() == 'Windows':
            blender_path = sorted(Path.joinpath(root, 'Program Files', 'Blender Foundation').glob('**/blender.exe'))
        elif platform.system() == 'Linux':
            blender_path = sorted(Path.joinpath(root).glob('**/blender'))
        else:
            blender_path = sorted(Path.joinpath(root, 'Applications').glob('**/blender'))
            
        #Location where the program folder will be created - user home directory subfolder called "SU_tool"
        tool_dir = Path.home() / 'SU_tool'
        tool_dir.mkdir(parents=True, exist_ok=True)
        print("tool dir: ", tool_dir)
        print(Path.joinpath(tool_dir, "Run BlenderGIS headless.py"))

        #Python script that gets saved to program folder
        script = "import bpy\nimport sys\nfrom pathlib import Path\nargv = sys.argv[7]\nprint(argv)\ntool_dir = Path.joinpath(Path.home(), 'SU_tool')\noutput = Path.joinpath(tool_dir,'tmp_SU.shp')\noutput1 = str(output)\nbpy.ops.wm.obj_import(filepath=argv, forward_axis='Y', up_axis='Z')\nbpy.ops.exportgis.shapefile(filepath=output1, objectsSource='SELECTED', exportType='POLYGONZ', mode='OBJ2FEAT')"
        filename = Path.joinpath(tool_dir, "Run BlenderGIS headless.py")
        if not filename.exists():
            filename.write_text(script)

        #Run Blender in Headless mode and export temporary shapefile
        subprocess.call([blender_path[0], '-b', '--addons', 'BlenderGIS-master', '--python', str(filename), '--', parameters['obj_file']], shell = True)

        # Fix geometries - Takes temporary shapefile exported by Blender
        temp_shp = Path.joinpath(tool_dir,"tmp_SU.shp")
        print("temp shp: ", temp_shp)
        alg_params = {
            'INPUT': str(temp_shp),
            'METHOD': 1,  # Structure
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['FixGeometries'] = processing.run('native:fixgeometries', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Dissolve
        alg_params = {
            'FIELD': [''],
            'INPUT': outputs['FixGeometries']['OUTPUT'],
            'SEPARATE_DISJOINT': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Dissolve'] = processing.run('native:dissolve', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Delete holes
        alg_params = {
            'INPUT': outputs['Dissolve']['OUTPUT'],
            'MIN_AREA': 0,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['DeleteHoles'] = processing.run('native:deleteholes', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Save local coordinate vector file
        alg_params = {
            'ACTION_ON_EXISTING_FILE': 0,  # Create or overwrite file
            'DATASOURCE_OPTIONS': '',
            'INPUT': outputs['DeleteHoles']['OUTPUT'],
            'LAYER_NAME': '',
            'LAYER_OPTIONS': '',
            'OUTPUT': str(local_path)
        }
        outputs['SaveVectorFeaturesToFile'] = processing.run('native:savefeatures', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        # Translate to Projected Coordinates - These can be changed if necessary
        alg_params = {
            'DELTA_M': 0,
            'DELTA_X': 452000,
            'DELTA_Y': 4413000,
            'DELTA_Z': 0,
            'INPUT': outputs['DeleteHoles']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Translate'] = processing.run('native:translategeometry', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        # Assign projection - Necessary after translating coordinates
        alg_params = {
            'CRS': QgsCoordinateReferenceSystem('EPSG:32632'),
            'INPUT': outputs['Translate']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['AssignProjection'] = processing.run('native:assignprojection', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        # Field calculator Year - Takes value input by user in "Year" and assigns to new field
        alg_params = {
            'FIELD_LENGTH': 0,
            'FIELD_NAME': 'Year',
            'FIELD_PRECISION': 0,
            'FIELD_TYPE': 1,  # Integer (32 bit)
            'FORMULA': parameters['year'],
            'INPUT': outputs['AssignProjection']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['FieldCalculatorYear'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}

        # Field calculator Trench - Create trench number and assigns to field "Trench"
        alg_params = {
            'FIELD_LENGTH': 0,
            'FIELD_NAME': 'Trench',
            'FIELD_PRECISION': 0,
            'FIELD_TYPE': 1,  # Integer (32 bit)
            'FORMULA': (math.floor(parameters['su_number']/1000))*1000,
            'INPUT': outputs['FieldCalculatorYear']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['FieldCalculatorTrench'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(8)
        if feedback.isCanceled():
            return {}

        # Field calculator SU - Takes SU number input by user and assigns to new field "SU"
        alg_params = {
            'FIELD_LENGTH': 0,
            'FIELD_NAME': 'SU',
            'FIELD_PRECISION': 0,
            'FIELD_TYPE': 1,  # Integer (32 bit)
            'FORMULA': parameters['su_number'],
            'INPUT': outputs['FieldCalculatorTrench']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['FieldCalculatorSu'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(9)
        if feedback.isCanceled():
            return {}

        # Save projected vector file
        alg_params = {
            'ACTION_ON_EXISTING_FILE': 0,  # Create or overwrite file
            'DATASOURCE_OPTIONS': '',
            'INPUT': outputs['FieldCalculatorSu']['OUTPUT'],
            'LAYER_NAME': '',
            'LAYER_OPTIONS': '',
            'OUTPUT': str(global_path)
        }
        outputs['SaveVectorFeaturesToFile'] = processing.run('native:savefeatures', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(10)
        if feedback.isCanceled():
            return {}

        # Load layer into project
        alg_params = {
            'INPUT': outputs['SaveVectorFeaturesToFile']['OUTPUT'],
            'NAME': global_filename
        }
        outputs['LoadLayerIntoProject'] = processing.run('native:loadlayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        return results

    def name(self):
        return 'Convert SU 3D OBJ to 3D SHP Polygon'

    def displayName(self):
        return 'Convert SU 3D OBJ to 3D SHP Polygon'

    def group(self):
        return ''

    def groupId(self):
        return ''

    def shortHelpString(self):
        return """<html><body><p><!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">
<html><head><meta name="qrichtext" content="1" /><style type="text/css">
</style></head><body style=" font-family:'MS Shell Dlg 2'; font-size:7.8pt; font-weight:400; font-style:normal;">
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;">This python script will take a 3D OBJ file representing the top of an SU and convert it to a shapefile using the BlenderGIS addon, and convert it to a single 3D polygon representing the boundaries of the SU. Fields for the SU number, trench, and excavation year will also be created. Two shapefiles, one in EPSG 32632 and the other in local coordinates, will be saved in the designated folder in Synology. The file will also be loaded into QGIS to quickly check that the output is correct.</p></body></html></p>
<h2>Input parameters</h2>
<h3>OBJ File</h3>
<p>This is the OBJ file of the top of the SU exported from CloudCompare</p>
<h3>Output File Path</h3>
<p>The folder where the shapefiles will be saved</p>
<h3>SU Number</h3>
<p>Enter the number of the SU</p>
<h3>Year</h3>
<p>The year in which the SU was excavated</p>
<h2>Outputs</h2>
<h3>Cleaned SU 3D Polygon</h3>
<p>The projected shapefile (in EPSG 32632) is loaded into QGIS to quickly verify the results. The files are automatically saved in the specified directory.</p>
<p><!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">
<html><head><meta name="qrichtext" content="1" /><style type="text/css">
</style></head><body style=" font-family:'MS Shell Dlg 2'; font-size:7.8pt; font-weight:400; font-style:normal;">
<p style="-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><br /></p></body></html></p><br><p align="right">Algorithm author: Matthew Notarian</p></body></html>"""

    def createInstance(self):
        return Convert3dOBJTo3dSHPPolygon()
