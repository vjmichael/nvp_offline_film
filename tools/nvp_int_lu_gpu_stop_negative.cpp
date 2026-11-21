// Independent Windows-native compile/negative and byte-parity fixture.
// Does NOT install a service, generate a key or claim GPU/Job custody.
#include "nvp_int_lu_gpu_stop_issuer.hpp"
#include <cstdio>
#include <exception>
int wmain() {
    using namespace nvp_int_lu_gpu_stop;
    const Original original{
        "gpu-abc123","dxgi:luid_0x12345678_0xabcdef12_phys_0",
        "nvp.film","film-1","conversation-1","turn-1","task-1",
        "epoch-1","session-1","ltx_111111111111111111111111"};
    try {
        auto canonical_body=canonical(original,42,123,57,890);
        if(canonical_body.size()<90 || canonical_body.front()!='L' ||
           canonical_body[sizeof(DOMAIN)-1]!=0) return 14;
        try {
            issue_after_original_job_empty(nullptr,nullptr,original,
                                           original.original_nvp_job_ref);
            return 15; // UNSAFE: null SCM Job was accepted.
        } catch(const std::exception&) { /* expected fail-closed */ }
        auto forged=original;forged.module_id="lu.ide";
        try{(void)canonical(forged,42,123,57,890);return 16;}
        catch(const std::exception&) { /* expected */ }
        auto foreign_job=original;foreign_job.original_nvp_job_ref="ltx_foreign";
        try{
           issue_after_original_job_empty(nullptr,nullptr,foreign_job,
                                           original.original_nvp_job_ref);
           return 17;
        }catch(const std::exception&) { /* expected */ }
        std::puts("NVP_GPU_01E_R2_NATIVE_RECEIPT_FORMAT_AND_DENIAL_PASS_NOT_INSTALLED");
        return 0;
    } catch(const std::exception&) {return 18;}
}
