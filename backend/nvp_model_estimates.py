"""STACK-02C3B3: source-verifiable CPU-only LM Studio memory estimate receipts.

This is admission *evidence*, not a prediction that the OS will stay healthy.
Only a trusted NVP host may invoke a SHA-pinned local CLI, with shell=False.
A supplied SHA string on its own is never a sufficient admission estimate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import subprocess
import time

from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_owned_models import OwnedCpuModelOperation

_SHA = re.compile(r"^[a-f0-9]{64}$")
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./@+-]{0,255}$")
_MEMORY = re.compile(r"(?m)^Estimated (GPU|Total) Memory:\s*([0-9]+(?:\.[0-9]{1,3})?)\s*(GB|GiB|MB|MiB)\s*$")
_MAX_STDOUT = 32768
_MAX_AGE_SECONDS = 300


def _hash_file(path):
    digest=sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",",":"), allow_nan=False)


def _mib(number, unit):
    value = float(number)
    if not math.isfinite(value) or value < 0:
        raise ValueError("Memory estimate was not a finite positive number")
    # Treat decimal 'GB' as GiB: over-reserve rather than under-reserve when
    # an external CLI does not declare its precise decimal/binary convention.
    return math.ceil(value * (1024 if unit in ("GB","GiB") else 1))


def parse_cpu_estimate(stdout, *, model_key):
    """Refuse altered, ambiguous, GPU-using or non-model-specific CLI output."""
    if not isinstance(stdout,str) or not 0<len(stdout.encode("utf8"))<=_MAX_STDOUT:
        raise ValueError("LM Studio estimate output was empty or oversized")
    if "\x1b" in stdout or "\x00" in stdout:
        raise ValueError("Terminal control characters not allowed in estimate")
    if not isinstance(model_key,str) or not _MODEL.fullmatch(model_key):
        raise ValueError("Unsafe or ambiguous local model key")
    names = re.findall(r"(?m)^Model:\s*(.+?)\s*$",stdout)
    if len(names)!=1 or names[0]!=model_key:
        raise ValueError("Estimator did not identify the exact requested model")
    measures = _MEMORY.findall(stdout)
    if len(measures)!=2 or set(item[0] for item in measures)!={"GPU","Total"}:
        raise ValueError("Expected exactly one GPU and one total memory reading")
    values={name:_mib(value,unit) for name,value,unit in measures}
    if values["GPU"] != 0:
        raise ValueError("CPU-only estimate unexpectedly requires GPU memory")
    total = values["Total"]
    if not 0<total<=65536:
        raise ValueError("Total memory estimate is missing or exceeds safe limit")
    # 25% estimate contingency plus 1 GiB host/allocator/runtime allowance.
    reserve = math.ceil(total*1.25)+1024
    if reserve>65536:
        raise ValueError("Estimated model exceeds the bounded resource governor")
    return {"estimated_total_mib":total,"estimated_gpu_mib":0,
            "conservative_ram_mb":reserve}


@dataclass(frozen=True)
class CpuEstimateReceipt:
    model_key: str
    context_length: int
    conservative_ram_mb: int
    estimated_total_mib: int
    estimated_gpu_mib: int
    captured_at: float
    cli_sha256: str
    output_sha256: str
    cli_args: tuple[str,...]
    format: str = "nvp.lms.cpu_estimate.v1"

    @property
    def digest(self):
        return sha256(_canonical(asdict(self)).encode("utf8")).hexdigest()

    def __post_init__(self):
        if (not _MODEL.fullmatch(self.model_key) or
            type(self.context_length) is not int or not 512<=self.context_length<=262144 or
            type(self.conservative_ram_mb) is not int or not 1024<=self.conservative_ram_mb<=65536 or
            type(self.estimated_total_mib) is not int or not 0<self.estimated_total_mib<=65536 or
            self.estimated_gpu_mib!=0 or
            not math.isfinite(self.captured_at) or
            not _SHA.fullmatch(self.cli_sha256) or not _SHA.fullmatch(self.output_sha256) or
            self.format!="nvp.lms.cpu_estimate.v1"):
            raise ValueError("Invalid trusted model estimate receipt")
        if self.conservative_ram_mb < math.ceil(self.estimated_total_mib*1.25)+1024:
            raise ValueError("Memory estimate omitted required contingency")
        if not isinstance(self.cli_args,(tuple,list)) or len(self.cli_args)!=9:
            raise ValueError("Unexpected CLI command contract")
        expected=("load","--estimate-only",self.model_key,"--context-length",
                  str(self.context_length),"--gpu","off","--host",self.cli_args[-1])
        if tuple(self.cli_args)!=expected or not re.fullmatch(r"127\.0\.0\.1:\d{4,5}",self.cli_args[-1]):
            raise ValueError("Estimate did not force a local CPU-only endpoint")


class TrustedLmsEstimator:
    def __init__(self, *, executable, executable_sha256, port=1234, runner=subprocess.run):
        path=Path(executable)
        if (not path.is_file() or path.is_symlink() or not _SHA.fullmatch(executable_sha256) or
            path.suffix.lower() in (".bat",".cmd",".ps1",".sh")):
            raise ValueError("A trusted native executable with a pinned SHA-256 is required")
        if type(port) is not int or not 1024<=port<=65535:
            raise ValueError("Estimate port must be an explicit unprivileged loopback port")
        if _hash_file(path)!=executable_sha256:
            raise ValueError("Local LM Studio CLI executable SHA mismatch")
        self.path=path.resolve()
        self.sha=executable_sha256
        self.port=port
        self.runner=runner

    def capture(self,model_key,context_length):
        if not isinstance(model_key,str) or not _MODEL.fullmatch(model_key):
            raise ValueError("Unsafe local model key")
        if type(context_length) is not int or not 512<=context_length<=262144:
            raise ValueError("Invalid model context")
        if _hash_file(self.path)!=self.sha:
            raise RuntimeError("Pinned local LM Studio estimator changed before use")
        args=("load","--estimate-only",model_key,"--context-length",
              str(context_length),"--gpu","off","--host",f"127.0.0.1:{self.port}")
        # This is an estimate, not a model load. Never shell out with the
        # creator's model key treated as a command or a shell fragment.
        process=self.runner([str(self.path),*args],shell=False,
                            capture_output=True,text=True,timeout=30,check=False)
        if process.returncode!=0:
            raise RuntimeError("LM Studio CPU estimate failed; model load refused")
        measured=parse_cpu_estimate(process.stdout,model_key=model_key)
        return CpuEstimateReceipt(
            model_key=model_key,context_length=context_length,
            **measured,captured_at=time.time(),cli_sha256=self.sha,
            output_sha256=sha256(process.stdout.encode("utf8")).hexdigest(),
            cli_args=args)


class EstimateStore:
    """Durable receipt provenance; a random hash never acts as estimation proof."""
    def __init__(self,ledger:TaskLedger):
        if not isinstance(ledger,TaskLedger):
            raise TypeError("A native TaskLedger is required")
        self.ledger=ledger
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS model_estimate_receipts (
                task_id TEXT PRIMARY KEY, digest TEXT NOT NULL,
                receipt_json TEXT NOT NULL, recorded_at REAL NOT NULL
            )""")

    def record(self,task_id,receipt:CpuEstimateReceipt):
        if not isinstance(receipt,CpuEstimateReceipt):
            raise TypeError("A verified native estimator receipt is required")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM model_estimate_receipts WHERE task_id=?",(task_id,)).fetchone():
                raise RuntimeError("Estimate task ID already sealed")
            db.execute("""INSERT INTO model_estimate_receipts(task_id,digest,receipt_json,recorded_at)
                VALUES(?,?,?,?)""",
                (task_id,receipt.digest,_canonical(asdict(receipt)),time.time()))
            db.commit()
        return receipt.digest

    def verify(self,operation:OwnedCpuModelOperation, *, now=None):
        with self.ledger._db() as db:
            row=db.execute("""SELECT digest,receipt_json FROM model_estimate_receipts
                WHERE task_id=?""",(operation.task_id,)).fetchone()
        if row is None:
            raise PermissionError("No genuine trusted CPU estimate receipt recorded")
        digest,text=row
        if sha256(text.encode("utf8")).hexdigest()!=digest:
            raise RuntimeError("Model estimate receipt was modified")
        try:
            receipt=CpuEstimateReceipt(**json.loads(text))
        except (ValueError,TypeError,KeyError) as error:
            raise RuntimeError("Invalid persisted estimator receipt") from error
        if (receipt.digest!=digest or
            receipt.model_key!=operation.model_key or
            receipt.context_length!=operation.context_length or
            receipt.conservative_ram_mb!=operation.conservative_ram_mb or
            digest!=operation.estimate_sha256):
            raise PermissionError("Model request differs from approved native estimate")
        age=(time.time() if now is None else now)-receipt.captured_at
        if not 0<=age<=_MAX_AGE_SECONDS:
            raise RuntimeError("Model memory estimate expired; explicit new approval required")
        return receipt


def operation_from_estimate(task_id,receipt:CpuEstimateReceipt):
    return OwnedCpuModelOperation(
        task_id=task_id,model_key=receipt.model_key,
        context_length=receipt.context_length,
        conservative_ram_mb=receipt.conservative_ram_mb,
        estimate_sha256=receipt.digest)
