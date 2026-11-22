"""Build strict runtime protobuf descriptors from the restricted NVP domain .proto.

This is a local `google.protobuf` DescriptorPool compile, NOT protoc/prost and
NOT a replacement for the later upstream pinned compiler gate. No native Lu
service/stub is built or installed. Reject unsupported syntax rather than
silently generating a mismatched contract.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

PACKAGE = "nvp.film.v1"
TYPES = {"string": 9, "bytes": 12, "uint64": 4, "uint32": 13, "bool": 8}
DECLARATION = re.compile(r"^(message|enum)\s+([A-Za-z]\w*)\s*\{$")
FIELD = re.compile(r"^(repeated\s+)?([A-Za-z]\w*)\s+([a-z]\w*)\s*=\s*(\d+)\s*;$")
ENUM_ITEM = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*(\d+)\s*;$")
EXPECTED = {
 "ProjectReadRequest", "ProjectReadResult", "SceneReadRequest", "SceneReadResult",
 "StoryProposalRequest", "StoryProposalResult", "ProjectCommitRequest", "ProjectCommitResult",
 "RenderShotRequest", "RenderShotResult", "PictureReviewReadRequest", "PictureReviewReadResult",
 "PictureReviewDecisionRequest", "PictureReviewDecisionResult", "FilmExportRequest", "FilmExportResult"
}

def compile_schema(text: str):
    clean = [line.split("//", 1)[0].strip() for line in text.splitlines()]
    lines = [line for line in clean if line]
    if lines[:2] != ['syntax = "proto3";', f"package {PACKAGE};"]:
        raise ValueError("Unexpected Protobuf package/syntax")
    file = descriptor_pb2.FileDescriptorProto()
    file.name = "nvp/film/v1/nvp_film_v1.proto"
    file.package = PACKAGE
    file.syntax = "proto3"
    current = None
    category = None
    for line in lines[2:]:
        if current is None:
            match = DECLARATION.fullmatch(line)
            if not match:
                raise ValueError(f"Unsupported declaration: {line}")
            category, name = match.groups()
            current = file.message_type.add() if category == "message" else file.enum_type.add()
            current.name = name
        elif line == "}":
            current = category = None
        elif category == "message":
            match = FIELD.fullmatch(line)
            if not match:
                raise ValueError(f"Unsupported field declaration: {line}")
            repeated, field_type, name, number = match.groups()
            if not 1 <= int(number) < 536870912:
                raise ValueError("Field number out of range")
            field = current.field.add()
            field.name = name
            field.number = int(number)
            field.label = 3 if repeated else 1
            if field_type in TYPES:
                field.type = TYPES[field_type]
            elif field_type == "PictureDecision":
                field.type = descriptor_pb2.FieldDescriptorProto.TYPE_ENUM
                field.type_name = f".{PACKAGE}.PictureDecision"
            else:
                raise ValueError(f"Unreviewed field type: {field_type}")
        else:
            match = ENUM_ITEM.fullmatch(line)
            if not match:
                raise ValueError(f"Unsupported enum declaration: {line}")
            item = current.value.add()
            item.name, number = match.groups()
            item.number = int(number)
    if current is not None:
        raise ValueError("Unclosed message/enum")
    names = [msg.name for msg in file.message_type]
    if len(names) != 16 or set(names) != EXPECTED or len(file.enum_type) != 1:
        raise ValueError("Unexpected NVP domain type set")
    enum = file.enum_type[0]
    if enum.name != "PictureDecision" or [(v.name,v.number) for v in enum.value] != [
        ("PICTURE_DECISION_UNSPECIFIED",0),
        ("PICTURE_DECISION_APPROVE",1),
        ("PICTURE_DECISION_REJECT",2),
    ]:
        raise ValueError("Review decision enum changed")
    for msg in file.message_type:
        fields = [v.number for v in msg.field]
        if len(fields) != len(set(fields)) or len(fields) == 0:
            raise ValueError("Duplicate field numbers or empty message")
    pool = descriptor_pool.DescriptorPool()
    pool.AddSerializedFile(file.SerializeToString())
    classes = {name: message_factory.GetMessageClass(pool.FindMessageTypeByName(f"{PACKAGE}.{name}"))
               for name in names}
    return file, classes


def compile_file(path: Path):
    return compile_schema(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    file, classes = compile_file(args.source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(file.SerializeToString(deterministic=True))
    print(json.dumps({"kind":"protobuf-runtime-descriptor-compile-NOT-protoc",
                      "package": file.package,"messages": sorted(classes),
                      "message_count": len(classes),"schema_bytes": args.source.stat().st_size,
                      "descriptor_bytes": args.out.stat().st_size,
                      "compiler_native_protoc_executed": False},indent=2))

if __name__ == "__main__":
    main()
