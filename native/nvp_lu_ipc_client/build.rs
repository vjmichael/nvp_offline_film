//! NVP-side source-locked prost generation; does not mutate Lu Core.
//! Set LU_WORKSPACE_PROTO to the checked-out Lu PR #244 workspace.proto.
//! Exact Git blob is pinned; if Lu changes protocol, review and repin first.
use sha1::{Digest,Sha1};
use std::{env,fs,path::PathBuf};
const LU_GIT_BLOB:&str="4e01d921197fb1c58c99958479b1cede36e13c9a";
fn main(){
    let lu=PathBuf::from(env::var_os("LU_WORKSPACE_PROTO")
        .expect("LU_WORKSPACE_PROTO must be independently checked-out Lu workspace.proto"));
    let bytes=fs::read(&lu).expect("Lu workspace.proto must exist as a real file");
    let mut hasher=Sha1::new();
    hasher.update(format!("blob {}\0",bytes.len()).as_bytes());
    hasher.update(&bytes);
    let actual=format!("{:x}",hasher.finalize());
    assert_eq!(actual,LU_GIT_BLOB,"Lu Core Protobuf source changed; explicit compatibility review required");
    // /proto/lu/workspace/v0/workspace.proto -> original Lu /proto root.
    let root=lu.ancestors().nth(4).expect("Unexpected Lu proto path");
    let nvp=PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../contracts/nvp/film/v1/nvp_film_v1.proto");
    let nvp_root=PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../contracts");
    assert!(nvp.is_file(),"NVP-owned film Protobuf absent");
    let protoc=protoc_bin_vendored::protoc_bin_path().expect("Pinned vendored protoc required");
    env::set_var("PROTOC",protoc);
    prost_build::Config::new().compile_protos(&[lu.clone(),nvp.clone()],
        &[root.to_path_buf(),nvp_root]).expect("Exact Lu/NVP Rust Protobuf compile required");
    println!("cargo:rerun-if-env-changed=LU_WORKSPACE_PROTO");
    println!("cargo:rerun-if-changed={}",lu.display());
    println!("cargo:rerun-if-changed={}",nvp.display());
}
