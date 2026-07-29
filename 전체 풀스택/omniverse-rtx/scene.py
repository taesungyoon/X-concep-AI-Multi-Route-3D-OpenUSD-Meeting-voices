from __future__ import annotations

from pathlib import Path


RENDER_PRODUCT_PATH = "/Render/OVServer/ViewportTexture0"


def validation_stage_usda(
    width: int, height: int, asset_path: str | Path | None = None
) -> str:
    """Build a self-contained stage used for renderer and stream readiness."""
    safe_width = max(1, int(width))
    safe_height = max(1, int(height))
    vertical_aperture = 20.955 * safe_height / safe_width
    if asset_path is None:
        inspection_part = '''def Sphere "InspectionPart"
    {
        float3[] extent = [(-50, -50, -50), (50, 50, 50)]
        color3f[] primvars:displayColor = [(0.08, 0.55, 0.95)]
        double radius = 50
        double3 xformOp:translate = (0, 55, 0)
        uniform token[] xformOpOrder = ["xformOp:translate"]
    }'''
    else:
        resolved_asset = Path(asset_path).expanduser().resolve()
        if not resolved_asset.is_file():
            raise FileNotFoundError(f"USD asset not found: {resolved_asset}")
        asset_uri = resolved_asset.as_posix().replace("@", "%40")
        inspection_part = f'''def Xform "InspectionPart" (
        prepend references = @{asset_uri}@
    )
    {{
    }}'''
    return f'''#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 0.01
    upAxis = "Y"
)

def Xform "World"
{{
    {inspection_part}

    def Cube "MachineBase"
    {{
        float3[] extent = [(-90, -18, -70), (90, 18, 70)]
        color3f[] primvars:displayColor = [(0.16, 0.19, 0.23)]
        double size = 2
        double3 xformOp:scale = (90, 18, 70)
        double3 xformOp:translate = (0, 18, 0)
        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
    }}

    def Cube "ControlCabinet"
    {{
        float3[] extent = [(-35, -70, -35), (35, 70, 35)]
        color3f[] primvars:displayColor = [(0.75, 0.78, 0.82)]
        double size = 2
        double3 xformOp:scale = (35, 70, 35)
        double3 xformOp:translate = (145, 70, 25)
        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
    }}

    def Mesh "Floor"
    {{
        float3[] extent = [(-350, 0, -280), (350, 0, 280)]
        int[] faceVertexCounts = [4]
        int[] faceVertexIndices = [0, 1, 2, 3]
        normal3f[] normals = [(0, 1, 0), (0, 1, 0), (0, 1, 0), (0, 1, 0)] (
            interpolation = "faceVarying"
        )
        point3f[] points = [(-350, 0, -280), (350, 0, -280), (350, 0, 280), (-350, 0, 280)]
        color3f[] primvars:displayColor = [(0.32, 0.34, 0.37)]
    }}

    def DistantLight "KeyLight"
    {{
        float angle = 1
        color3f color = (1, 0.96, 0.9)
        float intensity = 3500
        float3 xformOp:rotateXYZ = (315, 35, 0)
        uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]
    }}

    def DomeLight "FillLight"
    {{
        color3f inputs:color = (0.55, 0.68, 0.9)
        float inputs:intensity = 700
    }}
}}

def Camera "OVCamera"
{{
    float2 clippingRange = (1, 10000000)
    float focalLength = 24
    float horizontalAperture = 20.955
    float verticalAperture = {vertical_aperture:.6f}
    token projection = "perspective"
    float3 xformOp:rotateYXZ = (-21, 48, 24)
    double3 xformOp:translate = (360, 285, 390)
    uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateYXZ"]
}}

def "Render"
{{
    def "OVServer"
    {{
        def RenderProduct "ViewportTexture0" (
            prepend apiSchemas = ["OmniRtxSettingsCommonAdvancedAPI_1", "OmniRtxSettingsRtAdvancedAPI_1", "OmniRtxSettingsPtAdvancedAPI_1"]
        )
        {{
            rel camera = </OVCamera>
            token omni:rtx:background:source:type = "sky"
            token omni:rtx:rendermode = "RealTimePathTracing"
            rel orderedVars = [</Render/Vars/LdrColor>]
            uniform int2 resolution = ({safe_width}, {safe_height})
        }}
    }}

    def "Vars"
    {{
        def RenderVar "LdrColor"
        {{
            uniform string sourceName = "LdrColor"
        }}
    }}

    def RenderSettings "OVRenderSettings"
    {{
        rel products = [<{RENDER_PRODUCT_PATH}>]
    }}
}}
'''
