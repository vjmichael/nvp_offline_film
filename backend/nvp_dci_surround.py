"""DCI-P3A: explicit 48 kHz PCM24 theatrical routing and independent readback.

RDD 52:2020 sections 10.3.1-2, table 3. Restricted 16-channel container
without optional HI/VIN, motion, sync or sign-language tracks. No mix, gain,
resample, dither or implicit channel identification. These pure stream helpers
have no filesystem authority. A protected host supplies approved streams.
The numerical audit does NOT establish MXF MCA labels or projector acceptance.
"""
from __future__ import annotations
from hashlib import sha256
import re
import wave

BLOCK = 4096
SAMPLES_PER_EDIT_UNIT = 2000
SLOTS = 16
SHA = re.compile(r"[0-9a-f]{64}\Z")
# Input names are deliberately distinct for 5.1 and 7.1 side surrounds.
SOURCE_CHANNELS = {
    "5.1": ("L", "R", "C", "LFE", "Ls", "Rs"),
    "7.1DS": ("L", "R", "C", "LFE", "Lss", "Rss", "Lrs", "Rrs"),
}
# Producer lookup; audit below uses a separate, fixed slot->source definition.
ROUTE = {"5.1": (0, 1, 2, 3, 4, 5), "7.1DS": (0, 1, 2, 3, 4, 5, 10, 11)}


def validate_layout(profile, labels):
    if (type(profile) is not str or profile not in SOURCE_CHANNELS or
            type(labels) not in (list, tuple) or tuple(labels) != SOURCE_CHANNELS[profile]):
        raise ValueError("Explicit ordered source soundfield required; no implicit upmix")
    return len(SOURCE_CHANNELS[profile])


def _digest(value):
    if type(value) is not str or not SHA.fullmatch(value):
        raise PermissionError("Approved PCM SHA-256 required")
    return value


def _read_exact(stream, size):
    data = stream.read(size)
    if type(data) is not bytes or len(data) != size:
        raise ValueError("PCM stream truncated or invalid")
    return data


def route_block(source, profile, labels):
    """Interleaved signed little-endian PCM24. Return only a bounded block."""
    channels = validate_layout(profile, labels)
    if (type(source) is not bytes or not 0 < len(source) <= BLOCK*channels*3
            or len(source) % (channels*3)):
        raise ValueError("Bounded complete PCM24 sample frames required")
    import numpy as np
    samples = np.frombuffer(source, dtype=np.uint8).reshape(-1, channels, 3)
    mapped = np.zeros((len(samples), SLOTS, 3), dtype=np.uint8)
    mapped[:, ROUTE[profile], :] = samples
    return mapped.tobytes()


def write_mapped_reel(source, wav, *, profile, labels, edit_units, source_sha256):
    """Write one new derivative WAV to caller-owned private stage.

    A successful receipt requires exact source digest. The caller MUST discard
    unpublished output on any exception; this function cannot publish it.
    """
    channels = validate_layout(profile, labels)
    expected = _digest(source_sha256)
    if type(edit_units) is not int or not 24 <= edit_units <= 7200:
        raise ValueError("One-second minimum and bounded cinema reel required")
    total = edit_units*SAMPLES_PER_EDIT_UNIT
    src_hash, mapped_hash = sha256(), sha256()
    with wave.open(wav, "wb") as writer:
        writer.setnchannels(SLOTS)
        writer.setsampwidth(3)
        writer.setframerate(48000)
        writer.setnframes(total)
        for offset in range(0, total, BLOCK):
            count = min(BLOCK, total-offset)
            raw = _read_exact(source, count*channels*3)
            src_hash.update(raw)
            mapped = route_block(raw, profile, labels)
            mapped_hash.update(mapped)
            writer.writeframesraw(mapped)
        if source.read(1) or src_hash.hexdigest() != expected:
            raise PermissionError("Approved source reel length or digest differs")
    return {"profile":profile,"edit_units":edit_units,"samples_per_channel":total,
            "source_pcm_sha256":expected,"mapped_pcm_sha256":mapped_hash.hexdigest(),
            "container_channels":SLOTS,"source_modified":False,
            "mxf_channel_metadata_verified":False,"production_audio_accepted":False}


def verify_surround_reels(source, *, profile, labels, source_sha256, total_edit_units,
                          reels, open_reel):
    """Independent longplay-vs-reels readback, bounded by BLOCK samples.

    ``source`` is the trusted approved continuous raw master (not reconstructed
    from candidate reels). ``reels`` is the separately approved ordered ledger
    of exact reel id, start edit unit, duration, and mapped PCM SHA. ``open_reel``
    returns a caller-authorized context manager for the decoded reel WAV.
    Verifies complete raw sample equality, every reserved slot, per-channel
    hashes and ordered concatenation, independent of producer ROUTE.
    """
    channels = validate_layout(profile, labels)
    _digest(source_sha256)
    if (type(total_edit_units) is not int or not 24 <= total_edit_units <= 2592000 or
            type(reels) is not list or not 1 <= len(reels) <= 1000 or not callable(open_reel)):
        raise ValueError("Approved bounded feature/reel scope required")
    ledger=[]
    cursor=0
    ids=set()
    for entry in reels:
        if type(entry) is not dict or set(entry)!={"id","first_edit_unit","edit_units","mapped_pcm_sha256"}:
            raise ValueError("Exact reel identity and sample scope required")
        name, first, count, digest = (entry[k] for k in ("id","first_edit_unit","edit_units","mapped_pcm_sha256"))
        if (type(name) is not str or not name or len(name)>128 or name in ids or
                type(first) is not int or first!=cursor or type(count) is not int or not 24<=count<=7200):
            raise ValueError("Reel gap, overlap, duplicate, order or duration")
        ledger.append((name,first,count,_digest(digest)))
        ids.add(name); cursor+=count
    if cursor != total_edit_units:
        raise ValueError("Reels do not cover approved continuous master")
    slot_to_source = ((0,1,2,3,4,5,None,None,None,None,None,None,None,None,None,None)
                      if profile=="5.1" else
                      (0,1,2,3,4,5,None,None,None,None,6,7,None,None,None,None))
    import numpy as np
    source_hash, feature_hash = sha256(), sha256()
    channel_hashes=[sha256() for _ in range(SLOTS)]
    reports=[]
    for name,first,units,expected in ledger:
        total = units*SAMPLES_PER_EDIT_UNIT
        reel_hash=sha256()
        with open_reel(name) as handle, wave.open(handle,"rb") as reader:
            if (reader.getnchannels(),reader.getsampwidth(),reader.getframerate(),reader.getnframes(),reader.getcomptype()) != (SLOTS,3,48000,total,"NONE"):
                raise ValueError("Decoded reel WAV format or duration differs")
            for offset in range(0,total,BLOCK):
                count=min(BLOCK,total-offset)
                raw=_read_exact(source,count*channels*3)
                decoded=reader.readframes(count)
                if len(decoded)!=count*SLOTS*3:
                    raise ValueError("Decoded reel PCM truncated")
                source_hash.update(raw); reel_hash.update(decoded); feature_hash.update(decoded)
                original=np.frombuffer(raw,dtype=np.uint8).reshape(count,channels,3)
                actual=np.frombuffer(decoded,dtype=np.uint8).reshape(count,SLOTS,3)
                for slot,src in enumerate(slot_to_source):
                    channel=actual[:,slot,:]
                    if (np.any(channel) if src is None else not np.array_equal(channel,original[:,src,:])):
                        raise ValueError(f"PCM disagreement in reel {name}, container slot {slot+1}, sample block {offset}")
                    channel_hashes[slot].update(channel.tobytes())
            # RIFF's declared frame count can round down a partial final sample.
            if reader.readframes(1):
                raise ValueError("Unexpected trailing PCM sample bytes")
        if reel_hash.hexdigest()!=expected:
            raise PermissionError("Decoded reel SHA differs from approved mapping")
        reports.append({"id":name,"first_sample":first*SAMPLES_PER_EDIT_UNIT,
                        "end_sample_exclusive":(first+units)*SAMPLES_PER_EDIT_UNIT,
                        "mapped_pcm_sha256":expected})
    if source.read(1) or source_hash.hexdigest()!=source_sha256:
        raise PermissionError("Continuous original PCM length or SHA differs")
    return {"status":"SURROUND_PCM24_REFERENCE_EXACT","profile":profile,
            "source_channel_order":list(labels),"container_channels":SLOTS,
            "samples_per_channel":total_edit_units*SAMPLES_PER_EDIT_UNIT,
            "reel_count":len(ledger),"reels":reports,
            "source_pcm_sha256":source_sha256,"ordered_mapped_pcm_sha256":feature_hash.hexdigest(),
            "slot_sha256":[v.hexdigest() for v in channel_hashes],
            "silent_slots":[i+1 for i,v in enumerate(slot_to_source) if v is None],
            "all_samples_exact":True,"reel_continuity_verified":True,
            "mxf_channel_metadata_verified":False,"production_audio_accepted":False}

# Exact finite expressions reviewed against pinned asdcplib MXF.cpp parser.
# The pinned decoder never populates its used_soundfields map. Keep all
# 7.1DS channels within one group; hyphens advance the slot without a
# descriptor, including inside that group. Never repeat the group symbol.
MCA_EXPRESSION = {
    "5.1": "51(L,R,C,LFE,Ls,Rs),-,-,-,-,-,-,-,-,-,-",
    "7.1DS": "71(L,R,C,LFE,Lss,Rss,-,-,-,-,Lrs,Rrs),-,-,-,-",
}


def inspect_mxf_sound_metadata(raw, profile):
    """Verify pinned asdcp-info -H descriptor dump, independently of writer args.

    Exact field names are from pinned CineCert Metadata.cpp. Fails closed on
    absent, duplicate or mismatched labels, group links and assignment. This
    does not verify all ST 377-4 or ST 429-2 constraints.
    """
    if type(raw) is not bytes or not 0<len(raw)<=65536 or profile not in SOURCE_CHANNELS:
        raise ValueError("Bounded pinned native descriptor dump required")
    text=raw.decode("utf-8",errors="strict")
    objects=[]
    obj=None
    for line in text.splitlines():
        match=re.fullmatch(r"\s*[^\s]+\s+len:\s*\d+\s+\(([^()]+)\)\s*",line)
        if match:
            obj={"type":match.group(1)};objects.append(obj)
            continue
        field=re.fullmatch(r"\s+([A-Za-z][A-Za-z0-9]*)\s*=\s*(.*?)\s*",line)
        if obj is not None and field:
            key,value=field.groups()
            if key in obj:
                raise ValueError("Duplicate descriptor property")
            obj[key]=value
    def unique(kind):
        found=[o for o in objects if o["type"]==kind]
        if len(found)!=1: raise ValueError(f"Expected exactly one {kind}")
        return found[0]
    def hex16(value):
        if type(value) is not str or not re.fullmatch(r"[0-9a-fA-F. :\[\]-]+",value):
            raise ValueError("Malformed native 16-byte identifier")
        cleaned=re.sub(r"[. :\[\]-]","",value).lower()
        if len(cleaned)!=32 or cleaned=="0"*32: raise ValueError("Invalid native 16-byte identifier")
        return cleaned
    def ul(kind, number):
        return "060e2b340401010d0302"+kind+f"{number:02x}"+"00000000"
    wave_obj=unique("WaveAudioDescriptor")
    if (hex16(wave_obj.get("ChannelAssignment"))!="060e2b340401010b0402021003010400" or
            wave_obj.get("ChannelCount")!="16" or wave_obj.get("QuantizationBits")!="24" or
            wave_obj.get("AudioSamplingRate")!="48000/1"):
        raise ValueError("MXF sound assignment/rate/precision differs")
    group=unique("SoundfieldGroupLabelSubDescriptor")
    gnum=1 if profile=="5.1" else 2
    if (group.get("MCATagSymbol")!=("sg51" if gnum==1 else "sg71") or
            hex16(group.get("MCALabelDictionaryID"))!=ul("02",gnum) or "MCAChannelID" in group or
            "GroupOfSoundfieldGroupsLinkID" in text or any(o["type"]=="GroupOfSoundfieldGroupsLabelSubDescriptor" for o in objects)):
        raise ValueError("MXF soundfield group identity differs")
    group_id=hex16(group.get("MCALinkID"))
    expected = ({1:("L",1),2:("R",2),3:("C",3),4:("LFE",4),5:("Ls",5),6:("Rs",6)} if gnum==1 else
                {1:("L",1),2:("R",2),3:("C",3),4:("LFE",4),5:("Lss",7),6:("Rss",8),11:("Lrs",9),12:("Rrs",10)})
    seen={}; links={group_id}
    for obj in objects:
        if obj["type"]!="AudioChannelLabelSubDescriptor":continue
        value=obj.get("MCAChannelID", "")
        if not re.fullmatch(r"[1-9][0-9]?",value): raise ValueError("Invalid MCA slot")
        slot=int(value)
        if slot in seen or slot not in expected:raise ValueError("Unexpected or duplicate MCA slot")
        label,number=expected[slot]
        identity=hex16(obj.get("MCALinkID"))
        if (identity in links or obj.get("MCATagSymbol")!="ch"+label or
                hex16(obj.get("MCALabelDictionaryID"))!=ul("01",number) or
                hex16(obj.get("SoundfieldGroupLinkID"))!=group_id):
            raise ValueError("Wrong MCA channel dictionary identity or group link")
        links.add(identity);seen[slot]=label
    if set(seen)!=set(expected):raise ValueError("MCA channel coverage incomplete")
    return {"profile":profile,"configuration_4_verified":True,"mca_slot_labels":seen,
            "mca_group_link_verified":True,"native_metadata_sha256":sha256(raw).hexdigest(),
            "complete_smpte_conformity_verified":False}
