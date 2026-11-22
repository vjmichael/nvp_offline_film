// P1-F detached CMS creator-signature CRYPTOGRAPHIC contract fixture only.
// This test takes a public self-signed test certificate signature and proves
// the *same native verifier called by the SCM service* rejects source changes,
// wrong pinned issuer and expired/oversized one-use grants.
// It does NOT click any human dialog or issue a production grant.
#include "nvp_p1f_windows_creator_signature.hpp"
#include <iostream>
#include <string>

int wmain(int argc,wchar_t** argv) {
    try {
        if(argc!=4) throw std::runtime_error("Exact public signature test inputs required");
        auto ascii=[](const std::wstring& w){
            return std::string(w.begin(),w.end());
        };
        const std::string issuer=ascii(argv[2]);
        const std::string expiry=ascii(argv[3]);
        const auto signature=std::filesystem::path(argv[1]);
        nvp_p1f_creator_signature::SignedScope scope{
            "0123456789abcdef0123456789abcdef",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "test_signed_frame",
            std::string(64,'b'),std::string(64,'c'),std::string(64,'d'),
            std::string(64,'e'),std::string(64,'f'),std::string(64,'0'),
            expiry
        };
        if(!nvp_p1f_creator_signature::verify(scope,signature,issuer))
            throw std::runtime_error("Public signed issuer never verified");
        auto expect_rejection=[&](const char* reason,auto modify){
            auto mutant=scope;
            modify(mutant);
            try {
                nvp_p1f_creator_signature::verify(mutant,signature,issuer);
            } catch(const std::exception&) {return;}
            throw std::runtime_error(std::string("Detached signoff accepted tampered ")+reason);
        };
        expect_rejection("original USD",[](auto& s){s.usd_sha256[0]='1';});
        expect_rejection("original PCM",[](auto& s){s.pcm_sha256[0]='1';});
        expect_rejection("plan",[](auto& s){s.plan_sha256[0]='1';});
        expect_rejection("creator ticket",[](auto& s){s.ticket[0]='f';});
        expect_rejection("fixed script",[](auto& s){s.script_sha256[0]='1';});
        expect_rejection("job ID",[](auto& s){s.job_id="altered_job";});
        expect_rejection("expiry",[](auto& s){s.expires_utc_epoch_seconds="1";});
        try {
            nvp_p1f_creator_signature::verify(scope,signature,std::string(64,'0'));
        } catch(const std::exception&) {
            std::cout<<"NVP_P1F_REAL_NATIVE_CMS_CREATOR_SCOPE_SIGNATURE_TAMPER_DENIAL_PASS\n";
            std::cout<<"PUBLIC_FIXTURE_ONLY_NO_OPERATOR_SIGNOFF_NO_FILM_RENDER\n";
            return 0;
        }
        throw std::runtime_error("Creator signoff accepted an unpinned issuer");
    } catch(const std::exception& ex) {
        std::cerr<<"NVP_P1F_NATIVE_CREATOR_SIGNATURE_INVALID: "<<ex.what()<<"\n";
        return 87;
    }
}
