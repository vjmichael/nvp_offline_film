"""Ordered bounded hierarchy of already independently verified native file hashes.

This is supplementary receipt integrity, not a decoder, publication grant or
signature against an attacker controlling the entire protected journal.
"""
import hashlib
import json
import re

SHA = re.compile(r'[0-9a-f]{64}\Z')
FORMAT = 'nvp.feature.file_receipt_tree.v1'


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')


def digest(value):return hashlib.sha256(canonical(value)).hexdigest()


class ReceiptTree:
    """Binary carry tree, domain separated, with O(log n) live hash state."""
    def __init__(self, manifest_sha256):
        if type(manifest_sha256) is not str or not SHA.fullmatch(manifest_sha256):
            raise ValueError('Exact native feature manifest required')
        self.manifest=manifest_sha256;self.peaks=[];self.count=0;self.previous=None
    def add(self,name,sha):
        if (type(name) is not str or not 1<=len(name)<=128 or '/' in name or '\\' in name
            or type(sha) is not str or not SHA.fullmatch(sha) or (self.previous is not None and name<=self.previous)):
            raise PermissionError('Invalid or unordered output receipt leaf')
        leaf=digest(['file',self.count,name,sha]);self.previous=name;self.count+=1;level=0
        while level<len(self.peaks) and self.peaks[level] is not None:
            leaf=digest(['branch',level,self.peaks[level],leaf]);self.peaks[level]=None;level+=1
        if level==len(self.peaks):self.peaks.append(leaf)
        else:self.peaks[level]=leaf
    def finish(self):
        if not self.count:raise ValueError('Empty native receipt tree')
        return digest([FORMAT,self.manifest,self.count,[[i,p] for i,p in enumerate(self.peaks) if p is not None]])


def output_header(files,manifest_sha256,canonical_file_sha256):
    tree=ReceiptTree(manifest_sha256)
    for name in sorted(files):tree.add(name,files[name])
    return {'file_sha256':canonical_file_sha256,'tree_format':FORMAT,'receipt_tree_sha256':tree.finish()}


def check_output_header(header, canonical_file_sha256, tree):
    # Legacy native output pages have only the original flat digest. New
    # pages carry both, and unknown partial or malformed extensions fail.
    if header == {'file_sha256':canonical_file_sha256}:return
    expected={'file_sha256':canonical_file_sha256,'tree_format':FORMAT,'receipt_tree_sha256':tree.finish()}
    if header!=expected:raise PermissionError('Hierarchical output receipt differs')
