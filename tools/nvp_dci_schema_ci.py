"""Required external-XSD qualification on pinned libdcp schema mirrors.

Generated MXF placeholder bytes only; no essence/conformity claim. Uses all
three package writers; hostile mutations are covered in the source suite.
"""
import argparse
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from uuid import uuid4
from backend.nvp_wo4_file_dcp import _xml_package,_memory_digest
from backend.nvp_wo3_dcp_package import _compose_xml
from backend.nvp_wo4_multireel import _make_xml
from backend.nvp_dci_package_xsd import MIRROR_SCHEMAS, _blob, validate_official_package_xsd

REVIEWED_MIRROR_COMMIT = "277f5ff221b073a88111013612d6441928924cbc"

def materialize_reviewed_mirror(checkout, destination):
    """Read raw pinned Git objects, not line-ending-converted working files.

    Qualification-only trusted checkout; no fetching, shell, or schema URL.
    Validate every bounded blob before creating the fresh output directory.
    The independent XSD validator rechecks those same pins at readback.
    """
    checkout = Path(checkout).resolve(strict=True)
    destination = Path(destination)
    def git(*args):
        return subprocess.check_output(["git", "-C", str(checkout), *args],
                                       timeout=30)
    if git("rev-parse", "HEAD").strip().decode("ascii") != REVIEWED_MIRROR_COMMIT:
        raise PermissionError("Reviewed schema checkout commit differs")
    verified = {}
    for name, expected in MIRROR_SCHEMAS.values():
        ref = REVIEWED_MIRROR_COMMIT + ":xsd/" + name
        if git("rev-parse", ref).strip().decode("ascii") != expected:
            raise PermissionError("Reviewed schema tree blob mismatch: " + name)
        size = int(git("cat-file", "-s", expected))
        if not 0 < size <= 1024 * 1024:
            raise ValueError("Reviewed schema blob outside size bound")
        raw = git("cat-file", "blob", expected)
        if len(raw) != size or _blob(raw) != expected:
            raise PermissionError("Reviewed schema blob mismatch: " + name)
        verified[name] = raw
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    for name, raw in verified.items():
        with (destination / name).open("xb") as output:
            output.write(raw)
    return destination


def run(schemas):
    def uid():return str(uuid4())
    reports=[]
    for lane in ('memory','file','multireel'):
        ids={k:uid() for k in ('cpl','pkl','assetmap','reel','picture','sound')}
        issued='2026-11-19T12:00:00+00:00';media={'picture.mxf':b'not-real-picture'*100,'sound.mxf':b'not-real-sound'*100}
        if lane=='memory':
            files,_=_compose_xml({'asset_uuid':ids['picture'],'frame_count':24,'profile':'2K_FLAT_24','bytes':media['picture.mxf']},{'asset_uuid':ids['sound'],'frame_count':24,'bytes':media['sound.mxf']},title='Schema qualification',issued=issued)
        elif lane=='file':
            files={**media,**_xml_package(title='Schema qualification',issued=issued,ids=ids,profile='2K_FLAT_24',frames=24,metadata={k:_memory_digest(v) for k,v in media.items()})}
        else:
            parts=[];media={}
            for i in range(2):
                parts.append({'reel_uuid':uid(),'frames':24,'picture':{'asset_uuid':uid()},'sound':{'asset_uuid':uid()}})
                for kind in ('picture','sound'):media[f'{kind}_{i:04d}.mxf']=(kind+str(i)).encode()*100
            files={**media,**_make_xml(parts,{k:ids[k] for k in ('assetmap','pkl','cpl')},'Schema qualification',issued,{k:_memory_digest(v) for k,v in media.items()},'2K_FLAT_24')}
        with TemporaryDirectory() as temp:
            root=Path(temp)
            for name,data in files.items():(root/name).write_bytes(data)
            r=validate_official_package_xsd(root,schemas,source_set='LIBDCP_REVIEWED_MIRROR',expected_profile='2K_FLAT_24')
            if not r['reviewed_smpte_xsd_mirror_verified'] or r['production_dcp_accepted']:raise RuntimeError('XSD qualification did not pass honestly')
            reports.append({'writer':lane,'metadata_sha256':r['metadata_sha256'],'source_sha256':r['schema_source_sha256'],'reels':r['reel_count'],'native_essence_verified':False})
    return {'status':'REVIEWED_SMPTE_SCHEMA_MIRROR_XSD_PASS','reports':reports,'official_source_set_verified':False,'production_dcp_accepted':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('schema_folder')
    parser.add_argument('--reviewed-checkout', help='Extract exact pinned Git blobs into a fresh schema_folder before validation')
    args=parser.parse_args()
    if args.reviewed_checkout:
        materialize_reviewed_mirror(args.reviewed_checkout,args.schema_folder)
    print(json.dumps(run(args.schema_folder),sort_keys=True))
