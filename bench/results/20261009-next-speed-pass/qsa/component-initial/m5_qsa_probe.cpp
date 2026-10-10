#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-alloc.h"
#include <nlohmann/json.hpp>
#include <CommonCrypto/CommonDigest.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
using json = nlohmann::json;
using clock_type = std::chrono::steady_clock;
static void require(bool ok, const char * message) { if (!ok) throw std::runtime_error(message); }
static std::string hash_bytes(const void * p, size_t n) {
    unsigned char hash[CC_SHA256_DIGEST_LENGTH]; require(n <= UINT32_MAX, "Digest size overflow");
    CC_SHA256(p, CC_LONG(n), hash); char hex[65];
    for (size_t i = 0; i < sizeof(hash); ++i) std::snprintf(hex + 2*i, 3, "%02x", hash[i]); return hex;
}
struct spec { int pools, tokens; std::string kind; };
struct mask_graph { ggml_tensor * live, *indices, *output; };
struct resources {
    ggml_context * ctx = nullptr;
    ggml_backend_buffer_t buffer = nullptr;
    ggml_backend_sched_t sched = nullptr;
    ~resources() {
        if (sched) ggml_backend_sched_free(sched);
        if (buffer) ggml_backend_buffer_free(buffer);
        if (ctx) ggml_free(ctx);
    }
};
static mask_graph build_mask(ggml_context * ctx, ggml_tensor * score, ggml_tensor * pool_ids,
                            ggml_tensor * tail, ggml_tensor * kq, int n_kv, bool identity) {
    const int p = score->ne[0], t = score->ne[1], top = std::min(p, 512), n_sel = 4*top + 3;
    auto top_k = identity && p == top ? nullptr : ggml_top_k(ctx, score, top);
    auto sel_idx = top_k ? ggml_get_rows(ctx, pool_ids, ggml_reshape_1d(ctx, top_k, top*t)) :
        ggml_repeat_4d(ctx, ggml_reshape_2d(ctx, pool_ids, 4*p, 1), 4*p, t, 1, 1);
    sel_idx = ggml_reshape_2d(ctx, sel_idx, 4*top, t);
    sel_idx = ggml_concat(ctx, sel_idx, tail, 0);
    auto mask_all = ggml_new_tensor_4d(ctx, GGML_TYPE_F16, n_kv+n_sel, 1, 1, 1);
    mask_all = ggml_fill(ctx, mask_all, -INFINITY);
    mask_all = ggml_repeat_4d(ctx, mask_all, n_kv+n_sel, t, 1, 1);
    mask_all = ggml_reshape_3d(ctx, mask_all, 1, n_kv+n_sel, t);
    auto zeros = ggml_new_tensor_4d(ctx, GGML_TYPE_F16, n_sel, 1, 1, 1);
    zeros = ggml_fill(ctx, zeros, 0.0f);
    zeros = ggml_repeat_4d(ctx, zeros, n_sel, t, 1, 1);
    zeros = ggml_reshape_3d(ctx, zeros, 1, n_sel, t);
    auto top_score = top_k ? ggml_get_rows(ctx, ggml_reshape_3d(ctx, score, 1, p, t), top_k) :
        ggml_reshape_3d(ctx, score, 1, p, t);
    auto live_pool = ggml_clamp(ctx, ggml_scale_bias(ctx, top_score, 1.0f, 1.0f), 0.0f, 1.0f);
    live_pool = ggml_reshape_2d(ctx, ggml_repeat_4d(ctx, live_pool, 4, top, t, 1), 4*top, t);
    auto live_tail = ggml_cast(ctx, tail, GGML_TYPE_F32);
    live_tail = ggml_clamp(ctx, ggml_scale_bias(ctx, live_tail, -1.0f, float(n_kv)), 0.0f, 1.0f);
    auto live = ggml_concat(ctx, live_pool, live_tail, 0);
    auto dump = ggml_scale_bias(ctx, ggml_cumsum(ctx, ggml_fill(ctx, live, 1.0f)), 1.0f, float(n_kv-1));
    auto idx_f = ggml_cast(ctx, sel_idx, GGML_TYPE_F32);
    idx_f = ggml_add(ctx, ggml_mul(ctx, ggml_sub(ctx, idx_f, dump), live), dump);
    sel_idx = ggml_cast(ctx, idx_f, GGML_TYPE_I32);
    auto sel = ggml_set_rows(ctx, mask_all, zeros, ggml_reshape_3d(ctx, sel_idx, n_sel, t, 1));
    const size_t row = sel->nb[2];
    sel = ggml_view_4d(ctx, sel, n_kv, t, 1, 1, row, row*t, row*t, 0);
    sel = ggml_add(ctx, sel, kq);
    return { live, sel_idx, sel };
}
static json run_case(ggml_backend_t metal, ggml_backend_t cpu, const spec & s, bool identity, bool perf, std::ofstream & out) {
    const int p = s.pools, t = s.tokens, real = p-1, n_kv = ((4*real+3+63)/64)*64;
    require(n_kv + 4*p+3 < (1<<24), "Integer mask arithmetic too large");
    resources owned;
    auto ctx = owned.ctx = ggml_init({ggml_tensor_overhead()*512+ggml_graph_overhead_custom(512,false), nullptr, true});
    require(ctx, "Context creation failed"); auto graph = ggml_new_graph_custom(ctx,512,false);
    auto q = ggml_new_tensor_3d(ctx,GGML_TYPE_F32,128,4,t);
    auto k = ggml_new_tensor_3d(ctx,GGML_TYPE_F16,128,1,p);
    auto w = ggml_new_tensor_2d(ctx,GGML_TYPE_F32,4,t);
    auto pool_mask = ggml_new_tensor_2d(ctx,GGML_TYPE_F16,p,t);
    auto pool_ids = ggml_new_tensor_2d(ctx,GGML_TYPE_I32,4,p);
    auto tail = ggml_new_tensor_2d(ctx,GGML_TYPE_I32,3,t);
    auto kq = ggml_new_tensor_2d(ctx,GGML_TYPE_F16,n_kv,t);
    std::vector<ggml_tensor *> inputs={q,k,w,pool_mask,pool_ids,tail,kq};
    for (auto input: inputs) ggml_set_input(input);
    auto score = ggml_lightning_indexer(ctx,q,k,w,pool_mask);
    ggml_tensor * injected = nullptr;
    if (s.kind == "injected") {
        injected = ggml_new_tensor_2d(ctx,GGML_TYPE_F32,p,t); ggml_set_input(injected); inputs.push_back(injected); score = injected;
    }
    auto result = build_mask(ctx,score,pool_ids,tail,kq,n_kv,identity);
    ggml_set_output(score); ggml_set_output(result.live); ggml_set_output(result.indices); ggml_set_output(result.output);
    ggml_build_forward_expand(graph,score); ggml_build_forward_expand(graph,result.live);
    ggml_build_forward_expand(graph,result.indices);
    auto input_buffer = owned.buffer = ggml_backend_alloc_ctx_tensors(ctx,metal); require(input_buffer,"Input allocation failed");
    ggml_backend_t backends[]={metal,cpu}; auto sched=owned.sched=ggml_backend_sched_new(backends,nullptr,2,512,false,true);
    require(sched,"Scheduler failed");
    for (int i=0;i<ggml_graph_n_nodes(graph);++i) ggml_backend_sched_set_tensor_backend(sched,ggml_graph_node(graph,i),metal);
    require(ggml_backend_sched_alloc_graph(sched,graph),"Graph allocation failed");
    require(ggml_backend_sched_get_n_splits(sched)==1,"Unexpected scheduler split");
    std::vector<float> qv(128*4*t),wv(4*t,1.0f/std::sqrt(128.0f));
    std::vector<ggml_fp16_t> kv(128*p),mv(p*t),kqv(n_kv*t);
    std::vector<int32_t> piv(4*p,n_kv),tv(3*t,n_kv);
    for (size_t i=0;i<qv.size();++i) qv[i]=float(int((i*17+3)%61)-30)/64.0f;
    for (size_t i=0;i<kv.size();++i) kv[i]=ggml_fp32_to_fp16(float(int((i*13+11)%43)-21)/32.0f);
    if (s.kind=="zeros" || s.kind=="ties") std::fill(qv.begin(),qv.end(),s.kind=="zeros"?0.0f:1.0f);
    if (s.kind=="ties") std::fill(kv.begin(),kv.end(),ggml_fp32_to_fp16(1.0f));
    if (s.kind=="wide") std::fill(qv.begin(),qv.end(),65536.0f);
    if (s.kind=="inf") qv[0]=INFINITY;
    if (s.kind=="nan") { uint32_t bits=0x7fc00123; std::memcpy(qv.data(),&bits,4); }
    if (s.kind=="signed-zero") for (size_t i=0;i<qv.size();++i) qv[i]=i%2?-0.0f:0.0f;
    if (s.kind=="subnormal") std::fill(qv.begin(),qv.end(),std::ldexp(1.0f,-149));
    std::vector<int> cell(4*real+3); for (size_t i=0;i<cell.size();++i) cell[i]=s.kind=="permuted"?int(cell.size()-1-i):int(i);
    for (int block=0;block<real;++block) for (int j=0;j<4;++j) piv[4*block+j]=cell[4*block+j];
    for (int row=0;row<t;++row) {
        const int query=std::max(0,4*real+2-t+row), visible=std::min(real,(query+1)/4), ntail=(query+1)%4;
        for (int block=0;block<p;++block) mv[row*p+block]=ggml_fp32_to_fp16(block<visible?0.0f:-INFINITY);
        for (int j=0;j<ntail;++j) tv[row*3+j]=cell[4*visible+j];
        std::fill(kqv.begin()+row*n_kv,kqv.begin()+(row+1)*n_kv,ggml_fp32_to_fp16(-INFINITY));
        for (int pos=0;pos<=query;++pos) kqv[row*n_kv+cell[pos]]=ggml_fp32_to_fp16(0.0f);
    }
    auto set=[&](ggml_tensor * x,const auto & v){ggml_backend_tensor_set(x,v.data(),0,v.size()*sizeof(v[0]));};
    set(q,qv);set(k,kv);set(w,wv);set(pool_mask,mv);set(pool_ids,piv);set(tail,tv);set(kq,kqv);
    if(injected) {
        std::vector<float> sv(p*t); const uint32_t bits[]={0,0x80000000,0x3f800000,0x7f800000,0x7fc00123,0xffc00234,1};
        for(int row=0;row<t;++row)for(int block=0;block<p;++block){
            if(mv[row*p+block]==ggml_fp32_to_fp16(-INFINITY)) sv[row*p+block]=-INFINITY;
            else std::memcpy(&sv[row*p+block],&bits[block%7],4);
        }
        set(injected,sv);
    }
    std::vector<std::string> input_hash;
    for(auto x:inputs){std::vector<uint8_t> data(ggml_nbytes(x));ggml_backend_tensor_get(x,data.data(),0,data.size());input_hash.push_back(hash_bytes(data.data(),data.size()));}
    auto compute=[&](){require(ggml_backend_sched_graph_compute_async(sched,graph)==GGML_STATUS_SUCCESS,"Compute failed");ggml_backend_sched_synchronize(sched);};
    std::vector<double> samples; std::vector<int> iterations;
    compute();
    const int n_sel = 4*std::min(p,512)+3;
    std::vector<float> live_pre(n_sel*t); std::vector<int32_t> idx_pre(n_sel*t);
    ggml_backend_tensor_get(result.live,live_pre.data(),0,live_pre.size()*4);
    ggml_backend_tensor_get(result.indices,idx_pre.data(),0,idx_pre.size()*4);
    for(int row=0;row<t;++row){
        std::set<int32_t> used;
        for(int i=0;i<n_sel;++i){
            const float live=live_pre[row*n_sel+i]; const int index=idx_pre[row*n_sel+i];
            require(live==0.0f || live==1.0f,"Pre-scatter liveness is not binary");
            require(index>=0 && index<n_kv+n_sel,"Pre-scatter index is out of bounds");
            require(used.insert(index).second,"Pre-scatter duplicate index");
            require(live==0.0f || (index<n_kv && kqv[row*n_kv+index]==ggml_fp32_to_fp16(0.0f)),"Invisible pool is live");
        }
    }
    ggml_backend_sched_reset(sched);
    ggml_build_forward_expand(graph,result.output);
    require(ggml_backend_sched_alloc_graph(sched,graph),"Full graph allocation failed");
    compute();
    if(perf){
        auto warm=clock_type::now();do{compute();}while(std::chrono::duration<double>(clock_type::now()-warm).count()<0.5);
        for(int block=0;block<7;++block){auto started=clock_type::now();int n=0;double us;
            do{compute();++n;us=std::chrono::duration<double,std::micro>(clock_type::now()-started).count();}while(us<100000||n<8);
            samples.push_back(us/n);iterations.push_back(n);
        }
    }
    std::vector<float> scores(p*t),lives(ggml_nelements(result.live));
    std::vector<int32_t> indices(ggml_nelements(result.indices));std::vector<ggml_fp16_t> mask(n_kv*t);
    ggml_backend_tensor_get(score,scores.data(),0,scores.size()*4);
    ggml_backend_tensor_get(result.live,lives.data(),0,lives.size()*4);
    ggml_backend_tensor_get(result.indices,indices.data(),0,indices.size()*4);
    ggml_backend_tensor_get(result.output,mask.data(),0,mask.size()*2);
    bool binary=std::all_of(lives.begin(),lives.end(),[](float v){return v==0.0f||v==1.0f;});
    bool bounds=std::all_of(indices.begin(),indices.end(),[&](int i){return i>=0&&i<n_kv+4*std::min(p,512)+3;});
    require(binary&&bounds,"Nonbinary live or scatter bounds");
    if(p<=512 && (s.kind=="finite"||s.kind=="zeros"||s.kind=="ties"||s.kind=="signed-zero"||s.kind=="permuted"||s.kind=="subnormal"))
        require(mask==kqv,"Ordinary causal mask differs");
    for(size_t i=0;i<inputs.size();++i){std::vector<uint8_t> data(ggml_nbytes(inputs[i]));ggml_backend_tensor_get(inputs[i],data.data(),0,data.size());require(hash_bytes(data.data(),data.size())==input_hash[i],"Input cache/key/map changed");}
    const std::string id=std::to_string(p)+"/"+std::to_string(t)+"/"+s.kind;
    const auto mask_hash=hash_bytes(mask.data(),mask.size()*2),score_hash=hash_bytes(scores.data(),scores.size()*4);
    out<<json({{"id",id},{"mask_sha256",mask_hash},{"score_sha256",score_hash},{"mask_elements",mask.size()},{"input_sha256",input_hash}}).dump()<<'\n';
    auto sorted=samples;std::sort(sorted.begin(),sorted.end());
    json receipt={{"id",id},{"pools",p},{"tokens",t},{"kind",s.kind},{"identity",identity&&p<=512},{"mask_sha256",mask_hash},{"score_sha256",score_hash},
        {"input_sha256",input_hash},{"mask_elements",mask.size()},{"score_elements",scores.size()},{"live_binary",binary},{"scatter_in_bounds",bounds},{"inputs_preserved",true},
        {"all_nodes_metal",true},{"scheduler_splits",1},{"raw_nodes",ggml_graph_n_nodes(graph)},{"samples_us",samples},{"iterations",iterations},{"median_us",perf?sorted[3]:0}};
    return receipt;
}
int main(int argc,char ** argv){
    std::setvbuf(stdout,nullptr,_IOLBF,0);
    try{
        require(argc==4,"Usage: qsa-probe check|perf evidence.jsonl control|identity");
        const std::string mode=argv[1],scope=argv[3];require(mode=="check"||mode=="perf","Bad mode");require(scope=="control"||scope=="identity","Bad scope");
        std::ofstream out(argv[2]);require(bool(out),"Evidence file failed");
        ggml_backend_load_all();auto metal=ggml_backend_init_by_name("MTL0",nullptr);auto cpu=ggml_backend_init_by_type(GGML_BACKEND_DEVICE_TYPE_CPU,nullptr);require(metal&&cpu,"Backends failed");
        std::vector<spec> cases;
        if(mode=="perf")for(int p:{64,128,512,576})for(int t:{1,4,512})cases.push_back({p,t,"finite"});
        else {
            for(int p:{64,128,512,576})for(int t:{1,2,3,4,31,32,33,128,512})cases.push_back({p,t,"finite"});
            for(const std::string kind:{"zeros","ties","signed-zero","permuted","subnormal","wide","inf","nan","injected"})for(int t:{1,4,32})cases.push_back({64,t,kind});
        }
        for(const auto & s:cases){printf("M5_QSA_BEGIN %d/%d/%s\n",s.pools,s.tokens,s.kind.c_str());printf("M5_QSA_CASE %s\n",run_case(metal,cpu,s,scope=="identity",mode=="perf",out).dump().c_str());}
        printf("M5_QSA_DONE %s\n",json({{"mode",mode},{"scope",scope},{"cases",cases.size()},{"models_loaded",false}}).dump().c_str());
        ggml_backend_free(cpu);ggml_backend_free(metal);return 0;
    }catch(const std::exception & e){fprintf(stderr,"M5_QSA_ERROR %s\n",e.what());return 1;}
}
