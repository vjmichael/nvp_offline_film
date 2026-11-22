//! NVP-INT-LU-01E-GPU-01-R2: EXACT generated Lu native GPU lease wire.
//! No received Protobuf claim is authority to unload Lu, launch LTX or reload.
use nvp_lu_ipc_client::lu::{self,workspace_frame};
use prost::Message;
fn origin() -> lu::OriginRefs {
    lu::OriginRefs {
        workspace_ref:"film-1".into(), conversation_ref:"conversation-1".into(),
        user_turn_ref:"turn-1".into(),task_ref:"task-1".into(),
        operation_ref:"gpu-operation-1".into(),
    }
}
fn frame(body:workspace_frame::Body)->lu::WorkspaceFrame {
    lu::WorkspaceFrame {protocol_major:1,protocol_minor:0,
        request_id:"nvp-gpu-1".into(),session_ref:"core-session-1".into(),
        sequence:0,body:Some(body)}
}
#[test]
fn exact_gpu_request_is_not_gguf_inference_model_lease() {
    let req=lu::GpuLeaseRequest { origin:Some(origin()),
        device_ref:"dxgi:luid_0x12345678_0xabcdef12_phys_0".into(),
        required_free_vram_bytes:16*1024*1024*1024,max_duration_ms:600_000 };
    let f=frame(workspace_frame::Body::GpuLeaseRequest(req));
    let encoded=f.encode_to_vec();
    assert_eq!(lu::WorkspaceFrame::decode(encoded.as_slice()).unwrap(),f);
    assert!(matches!(f.body,Some(workspace_frame::Body::GpuLeaseRequest(_))));
}
#[test]
fn release_is_only_worker_stop_locator_not_credential_or_kernel_proof(){
    let release=lu::GpuLeaseRelease {origin:Some(origin()),
        lease_ref:"gpu-core-operation-1".into(),
        nvp_worker_stop_ref:"native-scm-stop-locator".into()};
    let f=frame(workspace_frame::Body::GpuLeaseRelease(release));
    assert_eq!(lu::WorkspaceFrame::decode(f.encode_to_vec().as_slice()).unwrap(),f);
    assert!(matches!(f.body,Some(workspace_frame::Body::GpuLeaseRelease(_))));
}
#[test]
fn original_gpu_poll_is_not_a_new_render_authorization(){
    let poll=lu::GpuLeasePoll{origin:Some(origin()),
        lease_ref:"gpu-core-operation-1".into(),
        // Assert the schema numeric identity and enum availability without
        // guessing prost's prefix-stripping variant name (Lu Core currently
        // has an E0599 from making that assumption in its own code).
        transition:1};
    let transition=lu::GpuLeaseTransitionKind::try_from(poll.transition)
        .expect("Lu schema must support acquired GPU poll transition");
    assert_eq!(transition.as_str_name(),"GPU_LEASE_TRANSITION_ACQUIRE");
    let request=frame(workspace_frame::Body::GpuLeasePoll(poll));
    assert_eq!(lu::WorkspaceFrame::decode(request.encode_to_vec().as_slice()).unwrap(),request);
    assert!(matches!(request.body,Some(workspace_frame::Body::GpuLeasePoll(_))));
}
#[test]
fn only_core_observation_and_phase_qualify_a_claim(){
    let answer=lu::GpuLeaseOutcome{operation_ref:"gpu-operation-1".into(),
        decision:lu::AdmissionDecision::Allowed as i32,
        phase:lu::GpuLeasePhase::Granted as i32,
        lease_ref:"gpu-core-operation-1".into(),
        measured_available_vram_bytes:Some(20*1024*1024*1024),
        reason_code:"GPU_READY".into()};
    let wire=frame(workspace_frame::Body::GpuLeaseOutcome(answer));
    assert_eq!(lu::WorkspaceFrame::decode(wire.encode_to_vec().as_slice()).unwrap(),wire);
    assert_eq!(lu::GpuLeasePhase::Restored as i32,5);
    assert_eq!(lu::GpuLeasePhase::Quarantined as i32,6);
}
