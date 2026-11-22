// NVP W1-G original first-party native worker capability slices.
//
// These are genuinely compiled role-specific executables with checked file I/O.
// They provide bounded intake, a mathematical picture test, PCM edits/gain, and
// a deterministic delivery bundle. They DO NOT implement device recording,
// OpenUSD/Cycles rendering, a nonlinear editor, spatial mastering, or SMPTE DCP.
// Production admission needs complete domain-specific implementations and a
// separate independent verifier before claiming full filmmaker capability.
//
// This code uses OS BCrypt (Windows) or reviewed libcrypto (Linux), no Python
// subprocess, shell, network, dynamic input path, arbitrary script or FFmpeg.
#include <algorithm>
#include <array>
#include <climits>
#include <utility>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
#pragma comment(lib,"bcrypt.lib")
#else
#include <openssl/sha.h>
#endif

#ifndef NVP_WORKER_ROLE
#error NVP_WORKER_ROLE must be supplied by the audited compiler
#endif

namespace fs=std::filesystem;
using Bytes=std::vector<unsigned char>;
static constexpr size_t NVP_WORKER_MAX_FILE_BYTES=8*1024*1024;
static const std::string ROLE=NVP_WORKER_ROLE;

static void require(bool ok,const char *message) {
    if(!ok)throw std::runtime_error(message);
}
static void verify_name(const fs::path &path) {
    require(path.filename()==path && !path.empty(),"Only bounded local worker files permitted");
    require(!fs::is_symlink(path),"Linked worker input/output forbidden");
}
static Bytes read_file(const std::string &name,size_t limit=NVP_WORKER_MAX_FILE_BYTES) {
    fs::path path(name);verify_name(path);
    require(fs::is_regular_file(path),"Required source/input absent");
    const auto len=fs::file_size(path);
    require(len>0 && len<=limit,"Source/input size out of bounds");
    std::ifstream in(path,std::ios::binary);
    require(bool(in),"Worker source/input open refused");
    Bytes bytes(static_cast<size_t>(len));
    in.read(reinterpret_cast<char *>(bytes.data()),std::streamsize(len));
    require(in.gcount()==std::streamsize(len),"Truncated original input");
    return bytes;
}
static void write_file(const std::string &name,const Bytes &data) {
    fs::path path(name);verify_name(path);
    require(!fs::exists(path),"Never overwrite original/previous worker output");
    require(!data.empty() && data.size()<=NVP_WORKER_MAX_FILE_BYTES+1024,
            "Worker output outside finite bounds");
    std::ofstream out(path,std::ios::binary|std::ios::out|std::ios::trunc);
    require(bool(out),"Worker output creation failed");
    out.write(reinterpret_cast<const char*>(data.data()),std::streamsize(data.size()));
    out.flush();
    require(bool(out),"Worker output incomplete");
}
static std::string hex_sha256(const Bytes &b) {
    std::array<unsigned char,32> digest{};
#ifdef _WIN32
    BCRYPT_ALG_HANDLE alg=nullptr;
    BCRYPT_HASH_HANDLE hash=nullptr;
    DWORD obj_size=0,cb=0,hash_size=0;
    require(BCryptOpenAlgorithmProvider(&alg,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0,
            "Native SHA-256 provider unavailable");
    std::vector<unsigned char> obj;
    bool ok=false;
    do {
        if(BCryptGetProperty(alg,BCRYPT_OBJECT_LENGTH,
            reinterpret_cast<PUCHAR>(&obj_size),sizeof(obj_size),&cb,0)<0)break;
        if(BCryptGetProperty(alg,BCRYPT_HASH_LENGTH,
            reinterpret_cast<PUCHAR>(&hash_size),sizeof(hash_size),&cb,0)<0)break;
        if(hash_size!=32 || obj_size>1048576)break;
        obj.resize(obj_size);
        if(BCryptCreateHash(alg,&hash,obj.data(),obj_size,nullptr,0,0)<0)break;
        if(b.size()>ULONG_MAX)break;
        if(BCryptHashData(hash,const_cast<PUCHAR>(b.data()),ULONG(b.size()),0)<0)break;
        if(BCryptFinishHash(hash,digest.data(),32,0)<0)break;
        ok=true;
    }while(false);
    if(hash)BCryptDestroyHash(hash);
    BCryptCloseAlgorithmProvider(alg,0);
    require(ok,"Native SHA-256 operation failed");
#else
    require(SHA256(b.data(),b.size(),digest.data())!=nullptr,
            "Native SHA-256 operation failed");
#endif
    const char chars[]="0123456789abcdef";
    std::string ret;ret.reserve(64);
    for(unsigned char c:digest){ret.push_back(chars[c>>4]);ret.push_back(chars[c&15]);}
    return ret;
}
static Bytes ascii(const std::string &value){return Bytes(value.begin(),value.end());}
static std::string parse_json_top_level(const std::string &text,const std::string &key){
    // Extract exactly one top-level quoted identifier from the sealed host plan.
    // Nested strings/objects are skipped, never interpreted as authority.
    int depth=0;
    bool in_string=false,escaped=false;
    size_t start=0;
    std::string pending,found;
    int matches=0;
    bool expect_key=false,expect_value=false;
    for(size_t i=0;i<text.size();i++){
        const char c=text[i];
        if(in_string){
            if(escaped){escaped=false;continue;}
            if(c=='\\'){escaped=true;continue;}
            if(c=='"'){
                in_string=false;
                const std::string value=text.substr(start,i-start);
                if(depth==1 && expect_key){
                    pending=value;expect_key=false;
                }else if(depth==1 && expect_value){
                    if(pending==key){found=value;++matches;}
                    expect_value=false;pending.clear();
                }
            }
            continue;
        }
        if(c=='"'){
            in_string=true;start=i+1;
            if(depth==1 && !expect_value && !expect_key){
                // A quoted item after an object comma is a key.
                expect_key=true;
            }
        }else if(c=='{'){++depth;if(depth==1)expect_key=true;}
        else if(c=='}'){--depth;require(depth>=0,"Malformed plan nesting");}
        else if(c==':' && depth==1){expect_value=true;}
        else if(c==',' && depth==1){expect_key=true;expect_value=false;pending.clear();}
    }
    require(!in_string && depth==0 && matches==1,
            "Missing, ambiguous or malformed sealed worker identity");
    require(!found.empty() && found.size()<=120,"Unbounded sealed worker identity");
    for(char c:found)require(
        (c>='a'&&c<='z')||(c>='A'&&c<='Z')||
        (c>='0'&&c<='9')||c=='_'||c=='-',
        "Untrusted escape or character in sealed worker identity");
    return found;
}
static std::string field(const std::string &s,const std::string &key){
    return parse_json_top_level(s,key);
}
static uint16_t pcm16(const Bytes &b,size_t i){
    return uint16_t(b[i])|uint16_t(uint16_t(b[i+1])<<8);
}
static int sample(const Bytes &b,size_t offset){
    return int(int16_t(pcm16(b,offset)));
}
static void emit_sample(Bytes &b,int value){
    require(value>=-32768 && value<=32767,"PCM sample overflow");
    uint16_t bits=uint16_t(int16_t(value));
    b.push_back(unsigned(bits&255));
    b.push_back(unsigned((bits>>8)&255));
}
static std::pair<unsigned,unsigned> two_numbers(const Bytes &b,
                                                 unsigned amax,unsigned bmax){
    std::istringstream input(std::string(b.begin(),b.end()));
    unsigned x=0,y=0;char trailing='\0';
    require(bool(input>>x>>y) && !(input>>trailing),"Invalid numeric worker control");
    require(x<=amax && y<=bmax,"Unbounded numeric worker control");
    return {x,y};
}
struct Operation {
    Bytes result;
    std::string output;
    std::string operation;
};
static Operation capture(){
    auto input=read_file("source.pcm");
    require(input.size()%2==0,"PCM16 source not sample-aligned");
    int peak=0;
    for(size_t i=0;i<input.size();i+=2)
        peak=std::max(peak,std::abs(sample(input,i)));
    std::string report="format=nvp.w1g.pcm_intake.v1\nsamples="+
        std::to_string(input.size()/2)+"\npeak="+std::to_string(peak)+
        "\nsource_sha256="+hex_sha256(input)+"\n";
    auto out=ascii(report);
    write_file("capture.manifest",out);
    return {out,"capture.manifest","pcm16_verified_intake"};
}
static Operation render(){
    auto spec=read_file("scene.txt",64);
    const auto [width,height]=two_numbers(spec,128,128);
    require(width>=16 && height>=16,"Native scene picture dimensions invalid");
    std::ostringstream header;
    header<<"P6\n"<<width<<" "<<height<<"\n255\n";
    auto out=ascii(header.str());out.reserve(out.size()+size_t(width)*height*3);
    for(unsigned y=0;y<height;y++)for(unsigned x=0;x<width;x++){
        const double nx=(double(x)+0.5)/width*2.0-1.0;
        const double ny=1.0-(double(y)+0.5)/height*2.0;
        const double r2=nx*nx+ny*ny;
        double diffuse=0.0;
        if(r2<0.54*0.54){
            const double nz=std::sqrt(0.54*0.54-r2)/0.54;
            diffuse=std::max(0.0,(nx*(-0.4)+ny*0.6+nz*0.75));
        }
        out.push_back(unsigned(20+std::lround(205*diffuse)));
        out.push_back(unsigned(20+std::lround(80*diffuse)));
        out.push_back(unsigned(30+std::lround(60*diffuse)));
    }
    write_file("render.ppm",out);
    return {out,"render.ppm","bounded_native_math_picture"};
}
static Operation editorial(){
    const auto input=read_file("source.pcm");
    require(input.size()%2==0,"Editorial PCM16 source misaligned");
    const auto range=read_file("edit.txt",64);
    const auto [start,count]=two_numbers(range,4194304,4194304);
    const size_t samples=input.size()/2;
    require(count>0 && size_t(start)<samples && size_t(count)<=samples-start,
            "Editorial sample range outside source Take");
    const Bytes out(input.begin()+size_t(start)*2,
                    input.begin()+(size_t(start)+count)*2);
    write_file("edit.pcm",out);
    return {out,"edit.pcm","bounded_pcm_non_destructive_cut"};
}
static Operation audio(){
    const auto input=read_file("source.pcm");
    require(input.size()%2==0,"PCM16 source misaligned");
    const auto gain=read_file("gain.txt",64);
    const auto [num,den]=two_numbers(gain,8,8);
    require(den>=1,"Zero gain denominator");
    Bytes out;out.reserve(input.size());
    for(size_t i=0;i<input.size();i+=2){
        const int v=sample(input,i);
        const int32_t scaled=int32_t(v)*int32_t(num)/int32_t(den);
        emit_sample(out,std::clamp(int(scaled),-32768,32767));
    }
    write_file("mix.pcm",out);
    return {out,"mix.pcm","bounded_native_pcm_gain"};
}
static void append_u64(Bytes &b,uint64_t v){
    for(unsigned i=0;i<8;i++)b.push_back(unsigned((v>>(8*i))&255));
}
static Operation delivery(){
    const auto picture=read_file("render.ppm");
    const auto audio=read_file("mix.pcm");
    require(audio.size()%2==0,"Delivery input PCM16 misaligned");
    require(picture.size()>=16 && picture[0]=='P' && picture[1]=='6',
            "Delivery input lacks raster PPM");
    Bytes out=ascii("NVPW1G01");
    append_u64(out,picture.size());
    append_u64(out,audio.size());
    out.insert(out.end(),picture.begin(),picture.end());
    out.insert(out.end(),audio.begin(),audio.end());
    require(out.size()<=NVP_WORKER_MAX_FILE_BYTES+1024,"Delivery bundle exceeds safety bound");
    write_file("delivery.bundle",out);
    return {out,"delivery.bundle","finite_native_media_bundle"};
}
static std::string quote(const std::string &value){
    for(char c:value)require(
        (c>='a'&&c<='z')||(c>='A'&&c<='Z')||
        (c>='0'&&c<='9')||c=='_'||c=='-'||c=='.',
        "Untrusted JSON output identity");
    return "\""+value+"\"";
}
int main(int argc,char**argv){
    try {
        require(argc==3 && std::string(argv[1])=="--plan",
                "Worker requires exactly --plan <original sealed plan>");
        const fs::path p(argv[2]);
        // Windows may spell the same directory differently (case, 8.3,
        // long path, junction traversal) even when the kernel sees one file.
        // Compare ACTUAL directory identities rather than path strings:
        // this preserves the no-foreign-job-directory safety boundary.
        require(p.is_absolute() && p.filename()=="plan.json" &&
                fs::equivalent(p.parent_path(),fs::current_path()),
                "Worker plan must be in the current private supervised workspace");
        const auto plan=read_file("plan.json",1024*1024);
        const std::string raw(plan.begin(),plan.end());
        const auto job=field(raw,"job_id"),project=field(raw,"project_id");
        require(field(raw,"role")==ROLE,"Compiled worker role differs from sealed plan");
        Operation op;
        if(ROLE=="original_capture")op=capture();
        else if(ROLE=="scene_render")op=render();
        else if(ROLE=="editorial")op=editorial();
        else if(ROLE=="audio")op=audio();
        else if(ROLE=="delivery")op=delivery();
        else throw std::runtime_error("Unknown compiled worker domain");
        const std::string result=
            "{\"format\":\"nvp.w1g.native_worker_result.v1\","+
            std::string("\"job_id\":")+quote(job)+
            ",\"project_id\":"+quote(project)+
            ",\"role\":"+quote(ROLE)+
            ",\"plan_sha256\":"+quote(hex_sha256(plan))+
            ",\"output_name\":"+quote(op.output)+
            ",\"output_sha256\":"+quote(hex_sha256(op.result))+
            ",\"operation\":"+quote(op.operation)+
            ",\"output_bytes\":"+std::to_string(op.result.size())+
            ",\"full_film_pipeline_accepted\":false}\n";
        write_file("result.json",ascii(result));
        return 0;
    }catch(const std::exception&err){
        std::cerr<<"NVP native worker refused: "<<err.what()<<"\n";
        return 12;
    }
}
