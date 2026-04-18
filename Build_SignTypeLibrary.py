import ifcopenshell
import ifcopenshell.api.context
import ifcopenshell.api.unit
import ifcopenshell.api.georeference
import math
import os
import re
from platformdirs import user_desktop_path

image_root = "C:\\Users\\rickb\\OneDrive - Washington State Department of Transportation\\BIM for Infrastructure\\Signs\\MUTCD\\Source\\"
uri_root = "C:\\Users\\rickb\\OneDrive - Washington State Department of Transportation\\BIM for Infrastructure\\Signs\\MUTCD\\Library\\"
#uri_root = "https://www.wsdot.wa.gov/eesc/bridge/Signs/"

no_dimensions = []

def get_root_filename(path):
    """
    Returns the filename without its extension.
    Example: '/path/to/image_12x34.png' → 'image_12x34'
    """
    base = os.path.basename(path)          # image_12x34.png
    root, _ = os.path.splitext(base)       # ('image_12x34', '.png')
    return root

def get_extensions(path):
    """
    Returns the filename without its extension.
    Example: '/path/to/image_12x34.png' → 'image_12x34'
    """
    base = os.path.basename(path)          # image_12x34.png
    _, ext = os.path.splitext(base)       # ('image_12x34', '.png')
    return ext

def extract_code(filename: str) -> str:
    """
    Extracts the leading code from a filename.
    The code is assumed to be the first token before the first space.
    """
    return filename.split(" ", 1)[0]

def generate_polygon(width,height,sides,start_angle):
    angle_step = 2*math.pi/sides
    X = 0.5*width/math.cos(math.pi/sides)
    Y = 0.5*height/math.cos(math.pi/sides)
    points = [
        (
            X*math.cos(start_angle + i*angle_step),
            Y*math.sin(start_angle + i*angle_step),
            0.
        )
        for i in range(sides)
    ]

    return points

import re

no_dimensions = []

def extract_dimensions(filename):
    """
    Extracts width and height from patterns like '12.5x34', '5x9.2', or '120.75x300.1'.
    Returns (width, height) as floats, or None if no valid pattern is found.
    """
    # Matches integers or floats: 12, 12.5, .5, 0.75
    pattern = r'(\d+(?:\.\d+)?)[xX](\d+(?:\.\d+)?)'
    match = re.search(pattern, filename)

    if match:
        width = float(match.group(1))
        height = float(match.group(2))
        return width, height

    no_dimensions.append(filename)
    return None


def process_signs(root_folder,model,body_model_context):
    sign_types = []
    for dirpath, dirnames, filenames in os.walk(root_folder):
        folder_name = os.path.basename(dirpath)

        for filename in filenames:
            if filename.lower().endswith(".png"):
                full_path = os.path.join(dirpath, filename)

                if folder_name in SHAPE_HANDLERS:
                    handler = SHAPE_HANDLERS[folder_name]
                    print(f"Processing {get_root_filename(full_path)}")
                    sign_type = handler(full_path,model,body_model_context)
                    if sign_type:
                        sign_types.append(sign_type)
                else:
                    print(f"No handler for folder '{folder_name}', skipping {full_path}")
    
    return sign_types


def handle_rectangle(file_path,model,body_model_context):
    dims = extract_dimensions(file_path)
    if dims:
        w,h = dims
        points = generate_polygon(w,h,4,math.pi/4)
        indicies = [(1,2,3),(3,4,1)]
        return create_signtype(file_path,model,body_model_context,points,indicies)
    else:
        return None
    

def handle_triangle(file_path,model,body_model_context):
    dims = extract_dimensions(file_path)
    if dims:
        w,h = dims
        points = generate_polygon(w,h,3,math.pi/6)
        indicies = [(1,2,3)]
        return create_signtype(file_path,model,body_model_context,points,indicies)
    else:
        return None

def handle_octagon(file_path,model,body_model_context):
    dims = extract_dimensions(file_path)
    if dims:
        w,h = dims
        points = generate_polygon(w,h,8,math.pi/8.)
        indicies = [(1,2,3),(1,3,4),(1,4,5),(1,5,6),(1,6,7),(1,7,8)]
        return create_signtype(file_path,model,body_model_context,points,indicies)

def handle_diamond(file_path,model,body_model_context):
    dims = extract_dimensions(file_path)
    if dims:
        w,h = dims
        points = generate_polygon(w,h,4,0.)
        indicies = [(1,2,3),(3,4,1)]
        return create_signtype(file_path,model,body_model_context,points,indicies)
    else:
        return None

def handle_pentagon(file_path,model,body_model_context):
    dims = extract_dimensions(file_path)
    if dims:
        w,h = dims
        points = [(w/2.,-h/2.,0.),(w/2.,0.,0.),(0.,h/2.,0.),(-w/2.,0.,0.),(-w/2.,-h/2.,0.)]
        indicies = [(1,2,3),(3,4,5),(1,3,5)]
        return create_signtype(file_path,model,body_model_context,points,indicies)
    else:
        return None

def handle_crossbuck(file_path,model,body_model_context):
    dims = extract_dimensions(file_path)
    if dims:
        a,b = dims
        angle = math.pi/4.
        p1 = (0.,-0.5*b/math.sin(angle),0.)
        p2 = (0.5*(a-b)*math.cos(angle), -0.5*b/math.sin(angle) - 0.5*(a-b)*math.sin(angle),0.)
        p3 = (p2[0] + b*math.cos(angle), p2[1]+b*math.sin(angle), 0.)
        p4 = (0.5*b/math.cos(angle), 0., 0.)
        p5 = (p4[0]+0.5*(a-b)*math.cos(angle), 0.5*(a-b)*math.sin(angle), 0.)
        p6 = (p5[0]-b*math.cos(angle), p5[1] + b*math.sin(angle), 0.)
        p7 = (0., 0.5*b/math.sin(angle), 0.)
        p8 = (-p6[0], p6[1], p6[2])
        p9 = (-p5[0], p5[1], p5[2])
        p10 = (-p4[0], p4[1], p4[2])
        p11 = (-p3[0], p3[1], p3[2])
        p12 = (-p2[0], p2[1], p2[2])
        
        points = [p1,p2,p3,p4,p5,p6,p7,p8,p9,p10,p11,p12]
        
        indicies = [(1,2,3),(1,3,4),(4,5,6),(4,6,7),(7,8,9),(7,9,10),(10,11,12),(10,12,1),(1,4,7),(1,7,10)]
        
        return create_signtype(file_path,model,body_model_context,points,indicies)
    else:
        return None
        
SHAPE_HANDLERS = {
    "Rectangle": handle_rectangle,
    "Triangle": handle_triangle,
    "Octagon": handle_octagon,
    "Diamond": handle_diamond,
    "Pentagon": handle_pentagon,
    "CrossBuck": handle_crossbuck
}
    
def create_signtype(file_type,model,body_model_context,points,indicies):
    #
    # create IfcSignType that acts as a predefined cell
    #

    name = get_root_filename(file_type)
    tag = extract_code(name)
    ext = get_extensions(file_type)
    
    point_list = model.createIfcCartesianPointList3d(CoordList=points)
    sign_panel = model.createIfcTriangulatedFaceSet(Coordinates=point_list,CoordIndex=indicies)
    shape_representation = model.createIfcShapeRepresentation(ContextOfItems=body_model_context,RepresentationIdentifier="Body",RepresentationType="Tessellation",Items=[sign_panel])

    # define the sign face image
    image_texture = model.createIfcImageTexture(
        RepeatS = False,
        RepeatT = False,
        Mode = "DIFFUSE",
        URLReference = uri_root + name + ext
    )

    shading = model.createIfcSurfaceStyleRendering(
        SurfaceColour = model.createIfcColourRgb(Red=0.5,Green=0.5,Blue=0.5),
        ReflectanceMethod="NOTDEFINED"
    )

    surface_with_texture = model.createIfcSurfaceStyleWithTextures(
        Textures=[image_texture]
    )
        
    surface_style = model.createIfcSurfaceStyle(
        Name=name,
        Side="POSITIVE",
        Styles=[shading,surface_with_texture]
    )

    styled_item = model.createIfcStyledItem(
        Item=sign_panel,
        Styles=[surface_style]
    )

    # the geometric representation is reusable and is placed in an IfcRepresentationMap. Use (0,0,0) as a simple origin
    origin =  model.createIfcAxis2Placement3D(Location=model.createIfcCartesianPoint((0.,0.,0.)))
    rep_map = model.createIfcRepresentationMap(MappingOrigin=origin,MappedRepresentation=shape_representation)

    # create the IfcSignType
    sign_type = model.createIfcSignType(GlobalId=ifcopenshell.guid.new(),Name=name,PredefinedType="PICTORAL",Tag=tag,RepresentationMaps=[rep_map])
    
    return sign_type

def create_ifc():
    # create IFC model
    model = ifcopenshell.file(schema="IFC4X3")

    # basic model setup for project and site
    project = model.createIfcProject(GlobalId=ifcopenshell.guid.new(),Name="Sign Library")

    # set up system of units (must be done after IfcProject is created)
    length_unit = ifcopenshell.api.unit.add_conversion_based_unit(model,name="inch")
    ifcopenshell.api.unit.assign_unit(model,units=[length_unit])

    # set up geometric representation context
    geometric_representation_context = ifcopenshell.api.context.add_context(model,context_type="Model")
    body_model_context = ifcopenshell.api.context.add_context(model,context_type="Model",context_identifier="Body",target_view="MODEL_VIEW",parent=geometric_representation_context)

    sign_library = model.createIfcProjectLibrary(GlobalId=ifcopenshell.guid.new(),Name="Traffic Signs", RepresentationContexts=[body_model_context])
    sign_types = process_signs(image_root,model,body_model_context)
    model.createIfcRelDeclares(GlobalId=ifcopenshell.guid.new(),RelatingContext=sign_library,RelatedDefinitions=sign_types)

    model.createIfcRelDeclares(GlobalId=ifcopenshell.guid.new(),RelatingContext=project,RelatedDefinitions=[sign_library])

    desktop = user_desktop_path()
    output_file = f"{desktop}\\TrafficSignLibrary.ifc"
    print(output_file)
    model.write(output_file)
    
    if len(no_dimensions) != 0:
        print("")
        print("Signs without dimensions")
        for v in no_dimensions:
            print(v)
    


if __name__ == "__main__":
    create_ifc()
    print("Done")
