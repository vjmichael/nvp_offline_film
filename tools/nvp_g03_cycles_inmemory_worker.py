"""G03-F3 fixed trusted Blender/Cycles renderer, no original file paths.

This is launched ONLY by the native host using a locally SHA-pinned Blender
binary, OS process custody, a reviewed one-use operation, and a synthetic or
independently sandboxed source grant. It accepts a bounded, already-validated
in-memory USD geometry description over a binary pipe and emits an in-memory
PNG. It never saves .blend, source USD, a plaintext PNG, audio, or a render
cache to a file. It refuses external asset textures/plugins and any scripting.

Do not route live private films to Blender until AppContainer/file/network
sandbox isolation has been separately proven; Job Objects alone are not a
filesystem/network sandbox.
"""
from __future__ import annotations

import json
import math
import os
import struct
import sys
import zlib

MAGIC_IN=b"NVPCYCLESIN1"
MAGIC_OUT=b"NVPCYCLESOUT1"
MAX_SPEC=2*1024*1024
MAX_PNG=4*1024*1024
MAX_OBJECTS=128
MAX_VERTICES=80000
MAX_FACES=80000


def _read_exact(handle, count):
    payload=bytearray()
    while count:
        block=handle.read(count)
        if not block:
            raise RuntimeError("Missing complete trusted Blender source")
        payload.extend(block)
        count-=len(block)
    return bytes(payload)


def _typed_number(value):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError("Only bounded finite source coordinates")
    if abs(value)>100000:
        raise ValueError("Out-of-range source coordinate")
    return float(value)


def _decode_spec(raw):
    if not 0<len(raw)<=MAX_SPEC:
        raise ValueError("Scene preview specification oversize")
    doc=json.loads(raw.decode("utf8"))
    if (type(doc) is not dict or set(doc)!={"format","width","height","samples","objects"} or
            doc["format"]!="nvp.g03.cycles.source.v1"):
        raise ValueError("Only original-reviewed scene coverage supported")
    if (type(doc["width"]) is not int or not 32<=doc["width"]<=256 or
            type(doc["height"]) is not int or not 32<=doc["height"]<=256 or
            type(doc["samples"]) is not int or not 1<=doc["samples"]<=32):
        raise ValueError("Native render budget out of bounds")
    objs=doc["objects"]
    if not isinstance(objs,list) or not 1<=len(objs)<=MAX_OBJECTS:
        raise ValueError("At least one bounded scene object required")
    for obj in objs:
        if not isinstance(obj,dict) or set(obj)!={"kind","name","matrix","vertices","faces","size"}:
            raise ValueError("Unexpected source object fields")
        if (obj["kind"] not in ("Cube","Sphere","Mesh") or
                type(obj["name"]) is not str or
                not 1<=len(obj["name"])<=90 or
                "/" in obj["name"] or "\x00" in obj["name"]):
            raise ValueError("Unsupported source geometry")
        matrix=obj["matrix"]
        if (not isinstance(matrix,list) or len(matrix)!=4 or
                any(not isinstance(row,list) or len(row)!=4 for row in matrix)):
            raise ValueError("Source transform must be 4x4")
        for row in matrix:
            for v in row:_typed_number(v)
        _typed_number(obj["size"])
        if not 0.001<=obj["size"]<=10000:
            raise ValueError("Source geometry size out of bounds")
        verts=obj["vertices"];faces=obj["faces"]
        if obj["kind"]=="Mesh":
            if (not isinstance(verts,list) or not 3<=len(verts)<=MAX_VERTICES or
                    not isinstance(faces,list) or
                    not 1<=len(faces)<=MAX_FACES):
                raise ValueError("Bounded native mesh required")
            for p in verts:
                if not isinstance(p,list) or len(p)!=3:
                    raise ValueError("Vertex must have three coordinates")
                for v in p:_typed_number(v)
            for face in faces:
                if (not isinstance(face,list) or not 3<=len(face)<=256 or
                        any(type(i) is not int or not 0<=i<len(verts) for i in face)):
                    raise ValueError("Invalid native polygon")
        elif verts or faces:
            raise ValueError("Primitive cannot contain embedded mesh")
    return doc


def _chunk(chunk_type,body):
    return (struct.pack("!I",len(body))+chunk_type+body+
            struct.pack("!I",zlib.crc32(chunk_type+body)&0xffffffff))


def _png_rgba(width,height,pixels):
    """Encode float RGBA fully in memory, no plaintext file or external lib."""
    if len(pixels)!=width*height*4:
        raise RuntimeError("Blender did not expose the Cycles Render Result pixels")
    rows=[]
    for y in range(height-1,-1,-1):
        line=bytearray(b"\0")
        for x in range(width):
            base=(y*width+x)*4
            for i in range(4):
                p=float(pixels[base+i])
                if not math.isfinite(p):
                    raise RuntimeError("Nonfinite native Cycles pixel")
                line.append(max(0,min(255,int(round(p*255)))))
        rows.append(bytes(line))
    compressed=zlib.compress(b"".join(rows),6)
    data=(b"\x89PNG\r\n\x1a\n"+
          _chunk(b"IHDR",struct.pack("!IIBBBBB",width,height,8,6,0,0,0))+
          _chunk(b"IDAT",compressed)+_chunk(b"IEND",b""))
    if len(data)>MAX_PNG:
        raise RuntimeError("Native Cycles PNG exceeds preview limit")
    return data


def _render(doc):
    import bpy
    from mathutils import Matrix,Vector

    # Blender startup defaults may preserve scripts/workspace state: discard
    # them and build ONLY typed objects under factory-startup isolation.
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for item in doc["objects"]:
        kind=item["kind"]
        if kind=="Cube":
            bpy.ops.mesh.primitive_cube_add(size=item["size"])
        elif kind=="Sphere":
            bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,
                                                 radius=item["size"]*.5)
        elif kind=="Mesh":
            mesh=bpy.data.meshes.new("NVP_Protected_Mesh")
            mesh.from_pydata(item["vertices"],[],item["faces"])
            mesh.update()
            obj=bpy.data.objects.new(item["name"],mesh)
            bpy.context.collection.objects.link(obj)
            bpy.context.view_layer.objects.active=obj
        obj=bpy.context.view_layer.objects.active
        obj.name=item["name"]
        # USD stores vectors in a row-major source transform; Blender's
        # matrix convention requires transposition on the host's canonical
        # conversion. The already-reviewed JSON is column-transposed.
        obj.matrix_world=Matrix(item["matrix"])
        material=bpy.data.materials.new("NVP_Original_Neutral")
        material.diffuse_color=(0.58,0.67,0.73,1.0)
        obj.data.materials.clear();obj.data.materials.append(material)
    bpy.ops.object.camera_add(location=(5.0,-8.0,5.0))
    camera=bpy.context.object
    target=Vector((0.0,0.0,0.0))
    camera.rotation_euler=(target-camera.location).to_track_quat("-Z","Y").to_euler()
    camera.data.lens=35
    bpy.context.scene.camera=camera
    bpy.ops.object.light_add(type="AREA",location=(1.5,-3.0,6.0))
    bpy.context.object.data.energy=600
    bpy.context.object.data.shape="DISK"
    bpy.context.object.data.size=6.0
    scene=bpy.context.scene
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=doc["samples"]
    scene.render.resolution_x=doc["width"]
    scene.render.resolution_y=doc["height"]
    scene.render.resolution_percentage=100
    scene.render.film_transparent=False
    scene.render.image_settings.file_format="PNG"
    # write_still=False is mandatory: no file-backed render or .blend saved.
    bpy.ops.render.render(write_still=False)
    image=bpy.data.images.get("Render Result")
    if image is None:
        raise RuntimeError("Blender did not produce a real Render Result")
    return _png_rgba(doc["width"],doc["height"],list(image.pixels))


def main():
    inp=sys.stdin.buffer
    header=_read_exact(inp,len(MAGIC_IN)+4)
    if header[:len(MAGIC_IN)]!=MAGIC_IN:
        raise RuntimeError("Unrecognized trusted Blender pipe input")
    length=struct.unpack("!I",header[len(MAGIC_IN):])[0]
    if not 1<=length<=MAX_SPEC:
        raise ValueError("Blender request exceeds native budget")
    raw=_read_exact(inp,length)
    if inp.read(1):
        raise RuntimeError("Trailing arbitrary Blender commands refused")
    spec=_decode_spec(raw)
    picture=_render(spec)
    # Native Blender logs can precede this marker; the host searches for it
    # and rejects any appended content and invalid PNG CRCs.
    sys.stdout.flush()
    os.write(1,MAGIC_OUT+struct.pack("!I",len(picture))+picture)
    # Avoid Blender cleanup writing caches/config after the fully verified
    # in-memory output. OS Job Object cleanup is verified by the host.
    os._exit(0)


if __name__=="__main__":
    main()
