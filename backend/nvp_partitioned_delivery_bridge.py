"""Native audio-set -> original finite cinema delivery admission.

Reconstruction on PERF-03F, not recovered R2. No independent worker or publisher.
Only the native host passes the source index, journal and verifier. The original
attach_delivery transaction remains responsible for all cinema authorization.
"""
from copy import deepcopy
import re

SHA = re.compile(r'[0-9a-f]{64}\Z')
FORMAT = 'nvp.wo4.partitioned_pcm24_candidate.v1'


def verify_finite_selection(index, journal, project_id, job_id, receipt, reel_index,
                            *, frame_ticks, select, cancelled=lambda:False):
    if type(receipt) is not dict or receipt.get('format') != FORMAT or receipt.get('status') != 'PARTITIONED_PCM24_CANDIDATE_PUBLISHED':
        raise PermissionError('Verified partitioned audio candidate required')
    if type(reel_index) is not int or reel_index < 0 or type(frame_ticks) is not int or frame_ticks <= 0:
        raise ValueError('Exact reel and native Film Time required')
    receipt = deepcopy(receipt)
    root = receipt.get('manifest_sha256')
    if not isinstance(root,str) or not SHA.fullmatch(root):
        raise PermissionError('Exact audio manifest SHA required')
    job = journal.status_page(job_id,limit=1,expected_project_id=project_id)
    if job['project_id'] != project_id or job['state'] != 'OUTPUT_READY':
        raise PermissionError('Selected picture is not ready in this movie')
    reel = journal.reel(job_id)
    record = index.read_revision(project_id,reel['decision_id'],reel['decision_revision'])
    if record['kind'] != 'presentation' or record['document_sha256'] != reel['decision_sha256']:
        raise PermissionError('Frozen mastering decision differs')
    data = record['data']; tick=data.get('film_start_tick'); frames=reel['frame_count']
    if type(tick) is not int or tick < 0 or tick % frame_ticks or type(frames) is not int or not 3<=frames<=7200:
        raise PermissionError('Exact finite picture interval required')
    if cancelled(): raise InterruptedError('Audio selection cancelled')
    candidate=select(receipt,reel_index,expected_first_frame=tick//frame_ticks,
                     expected_frame_count=frames,cancelled=cancelled)
    provenance=partitioned_provenance(candidate,data,frames,frame_ticks)
    if provenance is None or provenance['manifest_sha256'] != root:
        raise PermissionError('Selected reel is not bound to approved audio set')
    if candidate.get('original_take_sha256') != reel['take_sha256']:
        raise PermissionError('Original Take differs')
    if cancelled(): raise InterruptedError('Audio selection cancelled')
    return candidate


def partitioned_provenance(candidate, decision, frames, frame_ticks):
    """Derive durable provenance for the existing native approval transaction.

    The real finite selector independently verifies the entire audio set.
    This function validates clock/digest metadata; it is not a file verifier.
    Legacy single-reel candidates have neither partitioned field.
    """
    if 'partitioned_manifest_sha256' not in candidate:
        return None
    root=candidate['partitioned_manifest_sha256']; first=candidate.get('first_frame')
    if (type(root) is not str or not SHA.fullmatch(root) or type(first) is not int or first<0
            or first*frame_ticks != decision.get('film_start_tick')
            or candidate.get('frame_count')!=frames
            or candidate.get('sample_rate')!=48000 or candidate.get('sample_width_bytes')!=3
            or candidate.get('original_take_sha256')!=decision.get('source_take_sha256')):
        raise PermissionError('Partitioned audio does not match original picture clock or Take')
    return {'manifest_sha256':root,'first_frame':first,'frame_count':frames,
            'first_sample':first*2000,'sample_count':frames*2000}
