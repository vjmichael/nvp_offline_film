"""Strict USD shading connection validation for immutable NVP source materials.

A matching source prim path is NOT enough: a USD document can connect to
an alternate output on that same shader, silently changing PBR material
semantics. All paths/names/types here are first-party authored contracts.
These checks do not open files, run shaders, or grant a renderer capability.
"""
from __future__ import annotations


def verify_output_connection(target, source_path, output_name, *,
                             output_type=None, input_type=None):
    from pxr import Sdf,UsdShade
    if not target:
        raise RuntimeError("Required original USD shading input is missing")
    if input_type is not None and target.GetTypeName()!=input_type:
        raise RuntimeError("Original USD shading input type changed")
    # GetConnectedSource() can return only the first source when an
    # attacker authors *multiple* connections. Refuse all duplicate,
    # invalid and extra connection paths before looking up that first.
    edges=target.GetAttr().GetConnections()
    expected=Sdf.Path(source_path+".outputs:"+output_name)
    if len(edges)!=1 or edges[0]!=expected:
        raise RuntimeError("Original USD shading connection has extra or incorrect edges")
    connection=target.GetConnectedSource()
    if (not connection or
            str(connection[0].GetPrim().GetPath())!=source_path or
            str(connection[1])!=output_name or
            connection[2]!=UsdShade.AttributeType.Output):
        raise RuntimeError("Original USD shading connection source or socket changed")
    port=UsdShade.Shader(connection[0].GetPrim()).GetOutput(output_name)
    if not port:
        raise RuntimeError("Connected original USD shader output is missing")
    if output_type is not None and port.GetTypeName()!=output_type:
        raise RuntimeError("Original USD shader output type changed")
    return True


def verify_shader_id(stage, path, expected):
    from pxr import UsdShade
    shader=UsdShade.Shader(stage.GetPrimAtPath(path))
    if (not shader or not shader.GetIdAttr() or
            str(shader.GetIdAttr().Get())!=expected):
        raise RuntimeError("Original USD shader type or source path changed")
    return shader


def verify_literal_input(shader,name,expected,*,type_name=None):
    inp=shader.GetInput(name)
    # A dangling or unresolved authored edge can be invisible to
    # HasConnectedSource(), yet become live under USD composition. Literal
    # settings are never allowed to carry *any* connection path.
    if not inp or inp.GetAttr().GetConnections():
        raise RuntimeError("Literal original USD shader setting rewired")
    if type_name is not None and inp.GetTypeName()!=type_name:
        raise RuntimeError("Original USD shader setting type changed")
    if inp.GetAttr().Get()!=expected:
        raise RuntimeError("Literal original USD shader setting changed")
    return True
