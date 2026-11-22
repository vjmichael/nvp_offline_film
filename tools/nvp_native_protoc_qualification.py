"""Exact NVP schema qualification with an external native protoc executable.

The runtime uses the native-compiled descriptor set; no handcrafted-only
parser or old protoc-generated Python module is counted as native success.
No Lu Core installation, IPC listener or effect authorization is created.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from tools.nvp_compile_domain_descriptor import compile_file as reviewed_source_parser

EXPECTED = (
    'ProjectReadRequest','ProjectReadResult','SceneReadRequest','SceneReadResult',
    'StoryProposalRequest','StoryProposalResult','ProjectCommitRequest',
    'ProjectCommitResult','RenderShotRequest','RenderShotResult',
    'PictureReviewReadRequest','PictureReviewReadResult',
    'PictureReviewDecisionRequest','PictureReviewDecisionResult',
    'FilmExportRequest','FilmExportResult',
)
NATIVE_EFFECT = {'READ_WORKSPACE':'ReadWorkspace', 'WRITE_WORKSPACE':'WriteWorkspace',
                 'EXECUTE':'ExecuteCode'}


def qualify(protoc: Path, source: Path, catalog: Path, descriptor_out: Path) -> dict:
    if not protoc.is_file() or not source.is_file() or not catalog.is_file():
        raise FileNotFoundError('Missing native compiler / NVP schema / catalog')
    proto_root = source.parents[3]
    rel_path = source.relative_to(proto_root).as_posix()
    descriptor_out.parent.mkdir(parents=True,exist_ok=True)
    command = [str(protoc),'--proto_path='+str(proto_root),
               '--descriptor_set_out='+str(descriptor_out),rel_path]
    finished = subprocess.run(command,check=False,stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,timeout=15)
    if finished.returncode != 0:
        raise RuntimeError('Native protoc rejected schema: '+finished.stderr.decode('utf8','replace')[:800])
    native = descriptor_pb2.FileDescriptorSet.FromString(descriptor_out.read_bytes())
    if len(native.file)!=1: raise AssertionError('Expected one original native schema')
    file = native.file[0]
    if file.name!=rel_path or file.syntax!='proto3' or file.package!='nvp.film.v1':
        raise AssertionError('Wrong native Protobuf descriptor identity')
    if file.dependency or file.service or len(file.message_type)!=16 or len(file.enum_type)!=1:
        raise AssertionError('Unauthorized dependencies/services/unknown film type set')
    if tuple(m.name for m in file.message_type)!=EXPECTED:
        raise AssertionError('Native message set changed')
    source_desc, source_classes = reviewed_source_parser(source)
    for compiled,parsed in zip(file.message_type,source_desc.message_type):
        if compiled.name!=parsed.name or len(compiled.field)!=len(parsed.field):
            raise AssertionError('Review parser/native compiler disagree on fields')
        for native_field,source_field in zip(compiled.field,parsed.field):
            for attr in ('name','number','type','label','type_name'):
                if getattr(native_field,attr)!=getattr(source_field,attr):
                    raise AssertionError(f'Native descriptor mismatch: {compiled.name}.{native_field.name}.{attr}')
    if [(x.name,x.number) for x in file.enum_type[0].value] != [
            ('PICTURE_DECISION_UNSPECIFIED',0),('PICTURE_DECISION_APPROVE',1),
            ('PICTURE_DECISION_REJECT',2)]:
        raise AssertionError('Invalid native PictureDecision enum')
    pool=descriptor_pool.DescriptorPool()
    pool.Add(file)
    native_classes={name:message_factory.GetMessageClass(pool.FindMessageTypeByName('nvp.film.v1.'+name)) for name in EXPECTED}
    scene=native_classes['SceneReadResult'](scene_ref='scene-1',revision=1,scene_sha256=b'x'*32,
                                          take_refs=['take-one'],production_bible_ref='bible-one')
    wire=scene.SerializeToString(deterministic=True)
    if native_classes['SceneReadResult'].FromString(wire)!=scene:
        raise AssertionError('Native descriptor runtime roundtrip failed')
    if source_classes['SceneReadResult'].FromString(wire).SerializeToString(deterministic=True)!=wire:
        raise AssertionError('Native and prior runtime descriptor bytes disagree')
    catalog_obj=json.loads(catalog.read_text('utf8'))
    if catalog_obj.get('schema_status')!='draft_unregistered_no_permissions':
        raise AssertionError('Catalog improperly claims runtime authorization')
    caps=catalog_obj['capabilities']
    if len(caps)!=8 or len({x['id'] for x in caps})!=8:
        raise AssertionError('Expected eight unique NVP film capabilities')
    effect_gaps=[]
    for item in caps:
        if not item['id'].startswith('nvp.film.') or item['input'] not in EXPECTED or item['output'] not in EXPECTED:
            raise AssertionError('Incorrect tool namespace or type URL')
        declared=item['effect_classes']
        if not declared or not set(declared).issubset(NATIVE_EFFECT):
            raise AssertionError('Unknown/unapproved effect declaration')
        if len(declared)>1:effect_gaps.append(item['id'])
    return {'status':'NATIVE_PROTOC_DESCRIPTOR_PASS_NOT_RUST_OR_INSTALLED',
        'protoc_executable':str(protoc),'protoc_version':subprocess.run([str(protoc),'--version'],capture_output=True,text=True,timeout=5).stdout.strip(),
        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'native_descriptor_sha256':hashlib.sha256(descriptor_out.read_bytes()).hexdigest(),
        'native_descriptor_bytes':descriptor_out.stat().st_size,
        'message_count':len(native_classes),'enum_count':1,'services':0,'catalog_capabilities':len(caps),
        'native_tool_descriptor_single_effect_gaps':effect_gaps,
        'nvp_lu_os_authenticated':False,'lu_native_rust_prost_compiled':False,
        'windows_pipe_connected':False}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--protoc',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--catalog',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    print(json.dumps(qualify(args.protoc,args.source,args.catalog,args.out),indent=2))
