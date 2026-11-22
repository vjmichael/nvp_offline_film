"""G09-F honest installed native runtime/codec licensing introspection.

FIRST-PARTY local host preflight. Never downloads runtime wheels, executes
arbitrary project code, visits a website or fabricates code-signing proof.
The installed desktop launcher should call runtime_report() in the REAL
frozen Python process. A static installer manifest alone CANNOT prove
actual audio devices, cinema mastering, GPU performance or legal approval.
"""
from __future__ import annotations
import importlib
import importlib.metadata
import importlib.util
import platform
import sys

FORMAT="nvp.g09f.native_distribution_runtime.v1"
MODULES={
    "pillow":{"module":"PIL","distribution":"Pillow",
        "role":"source SDR JPEG read/encode"},
    "numpy":{"module":"numpy","distribution":"numpy",
        "role":"accelerated 48k stereo native PCM metering"},
    "scipy":{"module":"scipy","distribution":"scipy",
        "role":"streaming K-weighted 48k sound analysis"},
    "openusd":{"module":"pxr","distribution":None,
        "role":"original OpenUSD scene evaluation"},
    "fastapi":{"module":"fastapi","distribution":"fastapi",
        "role":"local director API"},
    "sounddevice":{"module":"sounddevice","distribution":"sounddevice",
        "role":"native original microphone capture"}}

def runtime_report():
    packages={}
    for name,definition in MODULES.items():
        module=definition["module"];dist=definition["distribution"]
        entry={"purpose":definition["role"],"module":module,
            "module_found":importlib.util.find_spec(module) is not None,
            "distribution_version":None,
            "reported_license":None,
            "native_module_imported":False,
            "legal_attribution_independently_reviewed":False}
        if dist is not None:
            try:
                meta=importlib.metadata.metadata(dist)
                entry["distribution_version"]=importlib.metadata.version(dist)
                entry["reported_license"]=(meta.get("License-Expression") or
                    meta.get("License"))
            except importlib.metadata.PackageNotFoundError:pass
        if entry["module_found"]:
            try:
                importlib.import_module(module)
                entry["native_module_imported"]=True
            except (ImportError,RuntimeError,OSError):
                entry["native_module_imported"]=False
        packages[name]=entry
    needed=("pillow","numpy","scipy","openusd","fastapi")
    available=all(packages[x]["native_module_imported"] for x in needed)
    return {"format":FORMAT,
        "python":platform.python_version(),
        "os":platform.system(),"machine":platform.machine(),
        "frozen_installed_runtime":bool(getattr(sys,"frozen",False)),
        "distributor_integrity_or_code_signature_verified":False,
        "package_reproducibility_verified":False,
        "installer_uninstall_preservation_verified":False,
        "native_long_film_modules_available":available,
        "runtime_dependencies":packages,
        "official_smpte_dcp_delivery_claimed":False,
        "native_gpu_feature_length_acceptance_passed":False}
