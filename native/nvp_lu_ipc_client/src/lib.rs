//! NVP-only native protocol consumer, no Lu Core source or privilege mutation.
//! Source-only until independently built on actual Rust/prost Windows toolchain.
//! No installed broker, no signed Lu peer, no user-turn grants: production OFF.
use prost::Message;
use sha2::{Digest,Sha256};
use std::{fmt,time::Duration};
use tokio::{io::{AsyncRead,AsyncReadExt,AsyncWrite,AsyncWriteExt},time::timeout};

pub mod lu {include!(concat!(env!("OUT_DIR"),"/lu.workspace.v0.rs"));}
pub mod film {include!(concat!(env!("OUT_DIR"),"/nvp.film.v1.rs"));}

const MAX_FRAME:usize=262_144;
const IO_DEADLINE:Duration=Duration::from_secs(3);

#[derive(Debug,Clone,PartialEq,Eq)]
pub enum Refusal { MissingInstaller, InvalidPeer, InvalidFrame, IncompatibleWire,
                   Expired, InvalidCredential, Timeout, Io, InvalidHealth }
impl fmt::Display for Refusal {fn fmt(&self,f:&mut fmt::Formatter<'_>)->fmt::Result{
    write!(f,"Lu Core read-only IPC refused: {self:?}")
}}
impl std::error::Error for Refusal {}

fn bounded_name(s:&str)->bool{
    !s.is_empty() && s.len()<=128 && s.bytes().all(|b|
        b.is_ascii_alphanumeric()||matches!(b,b'-'|b'_'|b'.'|b':'|b'/'))
}
fn canonical(frame:&lu::WorkspaceFrame)->Result<Vec<u8>,Refusal>{
    if frame.protocol_major!=1 || frame.protocol_minor!=0{return Err(Refusal::IncompatibleWire)}
    if !bounded_name(&frame.request_id)||frame.sequence!=0 ||frame.body.is_none(){
        return Err(Refusal::InvalidFrame)
    }
    let handshake=matches!(frame.body.as_ref(),
        Some(lu::workspace_frame::Body::Hello(_)|
             lu::workspace_frame::Body::AuthChallenge(_)|
             lu::workspace_frame::Body::AuthProof(_)));
    let welcome=matches!(frame.body.as_ref(),Some(lu::workspace_frame::Body::Welcome(_)));
    if (handshake && !frame.session_ref.is_empty()) ||
       (!handshake && !welcome && !bounded_name(&frame.session_ref)) ||
       (welcome && !bounded_name(&frame.session_ref)) {
        return Err(Refusal::InvalidFrame)
    }
    let data=frame.encode_to_vec();
    if data.is_empty()||data.len()>MAX_FRAME{return Err(Refusal::InvalidFrame)}
    Ok(data)
}
async fn send<S:AsyncWrite+Unpin>(s:&mut S,f:&lu::WorkspaceFrame)->Result<(),Refusal>{
    let raw=canonical(f)?;
    timeout(IO_DEADLINE,async{
        s.write_all(&(raw.len() as u32).to_be_bytes()).await?;
        s.write_all(&raw).await?;
        s.flush().await
    }).await.map_err(|_|Refusal::Timeout)?.map_err(|_|Refusal::Io)
}
async fn receive<S:AsyncRead+Unpin>(s:&mut S)->Result<lu::WorkspaceFrame,Refusal>{
    let bytes=timeout(IO_DEADLINE,async{
        let mut head=[0u8;4];s.read_exact(&mut head).await.map_err(|_|Refusal::Io)?;
        let size=u32::from_be_bytes(head) as usize;
        if size==0||size>MAX_FRAME {return Err(Refusal::InvalidFrame)}
        let mut raw=vec![0u8;size];s.read_exact(&mut raw).await.map_err(|_|Refusal::Io)?;
        Ok::<Vec<u8>,Refusal>(raw)
    }).await.map_err(|_|Refusal::Timeout)??;
    let frame=lu::WorkspaceFrame::decode(bytes.as_slice()).map_err(|_|Refusal::InvalidFrame)?;
    if canonical(&frame)?!=bytes {return Err(Refusal::InvalidFrame)}
    Ok(frame)
}
fn hmac(key:&[u8;32], parts:&[&[u8]])->[u8;32]{
    let mut inner=[0x36u8;64];let mut outer=[0x5cu8;64];
    for i in 0..32 {inner[i]^=key[i];outer[i]^=key[i];}
    let mut digest=Sha256::new();digest.update(inner);
    for p in parts{digest.update(p);}
    let inner_hash=digest.finalize();
    let mut digest=Sha256::new();digest.update(outer);digest.update(inner_hash);
    digest.finalize().into()
}
fn same(x:&[u8], y:&[u8])->bool{
    if x.len()!=y.len(){return false}
    let mut diff=0u8;for (a,b) in x.iter().zip(y){diff|=*a^*b;}diff==0
}
fn request_id()->Result<String,Refusal>{
    let mut b=[0u8;16];getrandom::getrandom(&mut b).map_err(|_|Refusal::InvalidCredential)?;
    Ok(b.iter().map(|v|format!("{v:02x}")).collect())
}

/// Only the trusted, protected native installer broker may create these.
/// Private fields prevent NVP WebView, model text or a decoded protobuf from
/// constructing a credential-backed session. Actual broker not implemented.
pub struct VerifiedEnrollment {package:[u8;32], key:[u8;32]}
// Sensitive handshake material must never enter Debug / tracing output.
impl fmt::Debug for VerifiedEnrollment {
    fn fmt(&self,f:&mut fmt::Formatter<'_>)->fmt::Result {
        f.debug_struct("VerifiedEnrollment")
            .field("package", &"[REDACTED]")
            .field("key", &"[REDACTED]")
            .finish()
    }
}
impl Drop for VerifiedEnrollment {fn drop(&mut self){
    use std::sync::atomic::{compiler_fence,Ordering};
    for v in self.key.iter_mut(){unsafe{std::ptr::write_volatile(v,0)}}
    compiler_fence(Ordering::SeqCst);
}}

#[derive(Debug,Clone)]
pub struct HealthObservation {pub status_code:String,pub core_epoch:String,pub health_epoch:u64}

/// Fixture/private low-level consumer, not a constructor of OS trust.
/// The genuine Windows entry must first check the *same live pipe handle*'s
/// server process image, signer, package pin, identity and broker credential.
async fn exchange_health<S:AsyncRead+AsyncWrite+Unpin>(
    stream:&mut S, enrollment:&VerifiedEnrollment,
)->Result<HealthObservation,Refusal>{
    if enrollment.package.iter().all(|b|*b==0)||enrollment.key.iter().all(|b|*b==0){
        return Err(Refusal::InvalidCredential)
    }
    let req=request_id()?;
    let mut nonce=[0u8;32];getrandom::getrandom(&mut nonce).map_err(|_|Refusal::InvalidCredential)?;
    let hello=lu::WorkspaceFrame {protocol_major:1,protocol_minor:0,
        request_id:req.clone(),session_ref:String::new(),sequence:0,
        body:Some(lu::workspace_frame::Body::Hello(lu::Hello{
            claimed_module_id:"nvp.film".into(),
            claimed_role:lu::ModuleRole::Workspace as i32,
            claimed_package_sha256:enrollment.package.to_vec(),
            minimum_major:1,maximum_major:1,maximum_minor:0,
            requested_features:vec![],client_nonce:nonce.to_vec(),
        }))};
    let original=canonical(&hello)?;send(stream,&hello).await?;
    let challenge=receive(stream).await?;
    if challenge.request_id!=req||!challenge.session_ref.is_empty(){return Err(Refusal::InvalidPeer)}
    let server_nonce=match challenge.body{Some(lu::workspace_frame::Body::AuthChallenge(v))
        if v.server_nonce.len()==32 && v.server_nonce.iter().any(|b|*b!=0)=>v.server_nonce,
        _=>return Err(Refusal::InvalidPeer)};
    let proof=hmac(&enrollment.key,&[b"lu.workspace.client.v0\0",&original,&server_nonce]);
    send(stream,&lu::WorkspaceFrame{protocol_major:1,protocol_minor:0,
         request_id:req.clone(),session_ref:String::new(),sequence:0,
         body:Some(lu::workspace_frame::Body::AuthProof(lu::AuthProof{
            client_hmac_sha256:proof.to_vec(),
         }))}).await?;
    let welcome=receive(stream).await?;
    if welcome.request_id!=req||!bounded_name(&welcome.session_ref){return Err(Refusal::InvalidPeer)}
    let (session,mut accepted)=match welcome.body{
        Some(lu::workspace_frame::Body::Welcome(v))=> (welcome.session_ref,v),
        _=>return Err(Refusal::InvalidPeer)};
    if accepted.selected_major!=1 || accepted.selected_minor!=0||
        !bounded_name(&accepted.core_epoch_ref)||!accepted.enabled_features.is_empty() {
        return Err(Refusal::InvalidPeer)
    }
    let observed=accepted.server_hmac_sha256.clone();accepted.server_hmac_sha256.clear();
    let unsigned=accepted.encode_to_vec();
    let expected=hmac(&enrollment.key,&[b"lu.workspace.server.v0\0",&original,&server_nonce,
                                       session.as_bytes(),&unsigned]);
    if !same(&expected,&observed){return Err(Refusal::InvalidPeer)}
    let health_id=request_id()?;
    send(stream,&lu::WorkspaceFrame{protocol_major:1,protocol_minor:0,
        request_id:health_id.clone(),session_ref:session.clone(),sequence:0,
        body:Some(lu::workspace_frame::Body::Health(lu::HealthRequest{}))}).await?;
    let response=receive(stream).await?;
    if response.request_id!=health_id||response.session_ref!=session {
        return Err(Refusal::InvalidHealth)
    }
    match response.body{
        Some(lu::workspace_frame::Body::HealthReport(report))
            if report.connected&&report.module_id=="lu.core"&&report.epoch>0&&
               bounded_name(&report.status_code)=>
               Ok(HealthObservation{status_code:report.status_code,
                  core_epoch:accepted.core_epoch_ref,health_epoch:report.epoch}),
        _=>Err(Refusal::InvalidHealth)
    }
}

/// Compiling this source cannot enable NVP's production connection. The
/// actual signer/peer-token/protected-key broker and Core health dispatcher
/// must provide separately accepted native Windows custody first.
#[cfg(windows)]
pub async fn installed_windows_health() -> Result<HealthObservation,Refusal> {
    Err(Refusal::MissingInstaller)
}
#[cfg(not(windows))]
pub async fn installed_windows_health() -> Result<HealthObservation,Refusal> {
    Err(Refusal::MissingInstaller)
}

#[cfg(test)]mod tests{
    use super::*;
    #[test]fn names_and_hmac_domain_separation(){
        assert!(bounded_name("nvp.film"));assert!(!bounded_name("../evil?"));
        assert_ne!(hmac(&[9u8;32],&[b"lu.workspace.client.v0\0",b"x"]),
                   hmac(&[9u8;32],&[b"lu.workspace.server.v0\0",b"x"]));
    }
    #[test]fn debug_output_never_leaks_handshake_key(){
        let secret=[0x72;32];
        let installed=VerifiedEnrollment {package:[0x11;32],key:secret};
        let printed=format!("{:?}", installed);
        assert!(printed.contains("[REDACTED]"));
        assert!(!printed.contains(&format!("{:?}", secret)));
    }
    #[test]fn no_installed_broker_fails_closed(){
        let rt=tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
        assert_eq!(rt.block_on(installed_windows_health()).unwrap_err(),Refusal::MissingInstaller);
    }
}

// NVP-side, source-only protocol fixture. Does not call a Core dispatcher,
// elevate privileges, open a pipe, or create an installed production key.
// Run with the genuinely compiled Rust/prost crate before making an
// acceptance claim; Python source scans are NOT execution of these tests.
#[cfg(test)]
mod independent_wire_tests {
    use super::*;
    use lu::workspace_frame::Body;

    fn framed(request_id: &str, session_ref: &str, body: Body) -> lu::WorkspaceFrame {
        lu::WorkspaceFrame {
            protocol_major: 1, protocol_minor: 0,
            request_id: request_id.into(), session_ref: session_ref.into(),
            sequence: 0, body: Some(body),
        }
    }
    async fn fixture_core(
        stream: &mut tokio::io::DuplexStream,
        key: &[u8;32],
        tamper_welcome: bool,
        tamper_health: bool,
    ) -> Result<(),Refusal> {
        let hello = receive(stream).await?;
        let request = hello.request_id.clone();
        let Some(Body::Hello(claim)) = hello.body.as_ref() else {
            return Err(Refusal::InvalidFrame);
        };
        if claim.claimed_module_id != "nvp.film" ||
           claim.claimed_role != lu::ModuleRole::Workspace as i32 ||
           claim.claimed_package_sha256 != vec![0x44;32] ||
           claim.client_nonce.len()!=32 {
            return Err(Refusal::InvalidPeer);
        }
        let original = canonical(&hello)?;
        let nonce = vec![0x55;32];
        send(stream,&framed(&request,"",Body::AuthChallenge(
            lu::AuthChallenge { server_nonce: nonce.clone() }
        ))).await?;
        let proof=receive(stream).await?;
        if proof.request_id != request {return Err(Refusal::InvalidPeer)}
        let Some(Body::AuthProof(proof_data))=proof.body else {
            return Err(Refusal::InvalidPeer);
        };
        let expected=hmac(key,&[b"lu.workspace.client.v0\0", &original, &nonce]);
        if !same(&expected,&proof_data.client_hmac_sha256) {
            return Err(Refusal::InvalidPeer);
        }
        let session="core-session-one";
        let mut welcome=lu::Welcome {
            selected_major:1,selected_minor:0,core_epoch_ref:"core-epoch-one".into(),
            enabled_features:vec![],server_hmac_sha256:vec![],
        };
        let signed= hmac(key,&[b"lu.workspace.server.v0\0",&original,&nonce,
            session.as_bytes(),&welcome.encode_to_vec()]);
        welcome.server_hmac_sha256 = if tamper_welcome { vec![0;32] }
                                      else { signed.to_vec() };
        send(stream,&framed(&request,session,Body::Welcome(welcome))).await?;
        if tamper_welcome {return Ok(())} // client MUST reject before health.
        let health=receive(stream).await?;
        if health.session_ref!=session ||
           !matches!(health.body,Some(Body::Health(_))) {
            return Err(Refusal::InvalidHealth);
        }
        send(stream,&framed(&health.request_id,session,Body::HealthReport(
            lu::HealthReport {
                module_id: if tamper_health {"attacker"} else {"lu.core"}.into(),
                connected:true,status_code:"READY".into(),epoch:6,
            }
        ))).await?;
        Ok(())
    }
    fn key_and_package() -> VerifiedEnrollment {
        VerifiedEnrollment { package:[0x44;32],key:[0x77;32] }
    }
    #[tokio::test]
    async fn source_only_health_roundtrip_with_matching_session_mac() {
        let (mut client,mut core)=tokio::io::duplex(8192);
        let key=[0x77;32];
        let (server,observed)=tokio::join!(
            fixture_core(&mut core,&key,false,false),
            exchange_health(&mut client,&key_and_package()),
        );
        server.unwrap();
        let report=observed.unwrap();
        assert_eq!(report.status_code,"READY");
        assert_eq!(report.health_epoch,6);
        assert_eq!(report.core_epoch,"core-epoch-one");
    }
    #[tokio::test]
    async fn forged_welcome_does_not_enable_health() {
        let (mut client,mut core)=tokio::io::duplex(8192);
        let key=[0x77;32];
        let (server,result)=tokio::join!(
            fixture_core(&mut core,&key,true,false),
            exchange_health(&mut client,&key_and_package()),
        );
        server.unwrap();
        assert_eq!(result.unwrap_err(),Refusal::InvalidPeer);
    }
    #[tokio::test]
    async fn forged_health_module_refused_after_valid_mac() {
        let (mut client,mut core)=tokio::io::duplex(8192);
        let key=[0x77;32];
        let (server,result)=tokio::join!(
            fixture_core(&mut core,&key,false,true),
            exchange_health(&mut client,&key_and_package()),
        );
        server.unwrap();
        assert_eq!(result.unwrap_err(),Refusal::InvalidHealth);
    }
    #[tokio::test]
    async fn wrong_hmac_enrollment_refused() {
        let (mut client,mut core)=tokio::io::duplex(8192);
        let key=[0x44;32];
        let (server,result)=tokio::join!(
            fixture_core(&mut core,&key,false,false),
            exchange_health(&mut client,&key_and_package()),
        );
        assert_eq!(server.unwrap_err(),Refusal::InvalidPeer);
        assert!(result.is_err());
    }
    #[test]
    fn zero_size_and_version_rejected_before_write() {
        let empty=framed("request","",Body::Health(lu::HealthRequest{}));
        assert_eq!(canonical(&empty).unwrap_err(),Refusal::InvalidFrame);
        let mut wrong=framed("request","session",Body::Health(lu::HealthRequest{}));
        wrong.protocol_minor=1;
        assert_eq!(canonical(&wrong).unwrap_err(),Refusal::IncompatibleWire);
    }
}
