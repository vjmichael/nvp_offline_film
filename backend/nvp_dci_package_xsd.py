"""Offline, qualification-only XSD validation from reviewed external sources.

Schemas are not redistributed. Exact public SMPTE source blob IDs are pinned;
the two W3C imports are pinned to reviewed libdcp mirror files. This adapter
never retrieves schema locations from a package, never follows a network
URL, never substitutes a permissive XMLDSIG stub. XSD PASS alone is not
operational DCP conformity or an authenticated cinema master.
"""
from pathlib import Path
from hashlib import sha1, sha256
from backend.nvp_wo3_dcp_structure import NS_AM,NS_CPL,NS_PKL,_asset_file,_linked_entry,MAX_XML_BYTES
from backend.nvp_dci_package import inspect_cinema_package

DS='http://www.w3.org/2000/09/xmldsig#'
XML='http://www.w3.org/XML/1998/namespace'
XS='http://www.w3.org/2001/XMLSchema'
SCHEMAS={
    NS_CPL:('st429-7a-2006.xsd','47e5982c51dd658f8f9c9fe8f5a1de0f028b0824'),
    NS_PKL:('st429-8a-2007.xsd','53e697f651aa0cf4ebbd2964d3c73eba96b33c6a'),
    NS_AM:('st-429-9a-2014.xsd','b741c2bd333a0818cdb2a3c7ca569da8c91c6d60'),
    DS:('xmldsig-core-schema.xsd','f30e1b24d79e4e6a7421ad3fbdb7d47c862cee6a'),
    XML:('xml.xsd','d662b4236cd346b34b09c87ac9f9893904c2d5f3'),
}

MIRROR_SCHEMAS={**SCHEMAS,
    NS_CPL:("SMPTE-429-7-2006-CPL.xsd","1b36f5c6a5c601a08cd87b3da22bdec4a3ea90c7"),
    NS_PKL:("SMPTE-429-8-2006-PKL.xsd","01d10afe14685b9c9f57afa361ac1fe642803078"),
    NS_AM:("SMPTE-429-9-2007-AM.xsd","a4432fee05dee8539cb4b0e79223db31094a458f"),
}

def _blob(data):
    return sha1(b'blob '+str(len(data)).encode('ascii')+b'\0'+data).hexdigest()


def validate_official_package_xsd(folder, schema_folder, *, expected_profile=None, expected_reels=None, source_set="SMPTE_PUBLISHED"):
    """Trusted operator-selected exact-schema folder, not a UI/AI path grant.

    Validation uses the exact newly read XML bytes corresponding to the
    strict package audit. Only import location routing is normalized in
    memory; types, patterns, enumerations and schema constraints untouched.
    A source XSD compile error is failure, never a relaxed substitution.
    """
    from lxml import etree
    if source_set not in ("SMPTE_PUBLISHED","LIBDCP_REVIEWED_MIRROR"):
        raise ValueError("Unknown reviewed schema source set")
    pins=SCHEMAS if source_set=="SMPTE_PUBLISHED" else MIRROR_SCHEMAS
    root=Path(schema_folder)
    if not root.is_dir() or any(_linked_entry(p) for p in (root,*root.parents)):
        raise PermissionError('Trusted local reviewed schema directory required')
    root=root.resolve(strict=True)
    items={}; originals={}
    # Refuse any resolver callback while parsing the actual pinned bytes.
    class Deny(etree.Resolver):
        def resolve(self,url,public_id,context):
            raise OSError('External schema/DTD access forbidden')
    def parser(resolver):
        p=etree.XMLParser(resolve_entities=False,load_dtd=False,no_network=True,huge_tree=False)
        p.resolvers.add(resolver);return p
    for ns,(name,expected) in pins.items():
        file=_asset_file(root,name)
        with file.open('rb') as inp:raw=inp.read(1024*1024+1)
        if not 0<len(raw)<=1024*1024 or _blob(raw)!=expected:
            raise PermissionError('Reviewed schema blob mismatch: '+name)
        originals[ns]=sha256(raw).hexdigest()
        node=etree.fromstring(raw,parser(Deny()))
        if node.tag!='{'+XS+'}schema' or node.get('targetNamespace')!=ns:
            raise ValueError('Incorrect schema target namespace')
        for child in node:
            if child.tag=='{'+XS+'}import':
                dependency=child.get('namespace')
                if dependency not in pins or dependency==ns:
                    raise PermissionError('Unknown schema import dependency')
                child.set('schemaLocation','urn:nvp:reviewed-schema:'+pins[dependency][0])
            elif child.tag in ('{'+XS+'}include','{'+XS+'}redefine'):
                raise PermissionError('Unexpected schema include or redefine')
        items['urn:nvp:reviewed-schema:'+name]=etree.tostring(node,encoding='UTF-8')
    class LocalOnly(etree.Resolver):
        def resolve(self,url,public_id,context):
            if url not in items:raise OSError('Unreviewed schema resolution denied')
            return self.resolve_string(items[url],context,base_url=url)
    schemas={}
    for ns in (NS_CPL,NS_PKL,NS_AM):
        location='urn:nvp:reviewed-schema:'+pins[ns][0]
        schemas[ns]=etree.XMLSchema(etree.fromstring(items[location],parser(LocalOnly()),base_url=location))
    audit=inspect_cinema_package(folder,expected_profile=expected_profile,expected_reels=expected_reels)
    for name,ns in [('ASSETMAP.xml',NS_AM),('VOLINDEX.xml',NS_AM),('PKL.xml',NS_PKL),('CPL.xml',NS_CPL)]:
        with _asset_file(Path(folder),name).open('rb') as inp:raw=inp.read(MAX_XML_BYTES+1)
        if len(raw)>MAX_XML_BYTES or sha256(raw).hexdigest()!=audit['metadata_sha256'][name]:
            raise PermissionError('Package XML changed before XSD validation')
        schemas[ns].assertValid(etree.fromstring(raw,parser(Deny())))
    return {**audit,'official_smpte_xsd_verified':source_set=='SMPTE_PUBLISHED','reviewed_smpte_xsd_mirror_verified':source_set=='LIBDCP_REVIEWED_MIRROR','schema_source_set':source_set,'schema_source_sha256':originals,'production_dcp_accepted':False}
