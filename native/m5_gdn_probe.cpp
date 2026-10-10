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
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using json = nlohmann::json;
static constexpr float sentinel = 12345.0f;
static ggml_backend_t cpu_backend=nullptr;
static void require(bool ok, const char * message) { if (!ok) throw std::runtime_error(message); }

struct spec {
    int S=128, H=48, HQ=16, T=4, B=1, K=4, G=1;
    bool fused=true;
    bool padded_cache=true;
    std::string layout="model", label="target";
    uint32_t seed=0x725918;
};

static float sample(uint32_t index, uint32_t seed) {
    uint32_t x=index+seed; x^=x>>16; x*=0x7feb352d; x^=x>>15; x*=0x846ca68b; x^=x>>16;
    return float(int(x%200001)-100000)/100000.0f;
}
static bool bits_equal(const std::vector<float> & a, const std::vector<float> & b) {
    return a.size()==b.size() && std::memcmp(a.data(),b.data(),a.size()*sizeof(float))==0;
}

struct result {
    std::vector<float> attention, cache, tail, final_state;
    double attention_nmse=0, state_nmse=0, max_abs=0;
    float consumer_value=0;
    size_t evidence_elements=0, attention_values_checked=0, state_values_checked=0;
};

struct fixture {
    spec p;
    ggml_backend_t backend;
    ggml_context * ctx=nullptr;
    ggml_backend_buffer_t buffer=nullptr;
    ggml_backend_sched_t scheduler=nullptr;
    ggml_cgraph * graph=nullptr;
    ggml_tensor * out=nullptr, * cache=nullptr, * attention_out=nullptr, * consumer=nullptr;
    std::vector<std::pair<ggml_tensor *,std::vector<float>>> inputs;
    std::vector<float> q, k, v, g, beta, initial;
    size_t D, A, slot_stride, cache_offset;
    std::vector<size_t> qkv_view_offsets_bytes;

    fixture(ggml_backend_t backend, spec p, int token_offset=0, const std::vector<float> * restored=nullptr)
        : p(p), backend(backend), D(size_t(p.S)*p.S*p.H*p.B), A(size_t(p.S)*p.H*p.T*p.B), slot_stride(D+(p.padded_cache?37:0)), cache_offset(p.padded_cache?11:D) {
        ctx=ggml_init({ggml_tensor_overhead()*128+ggml_graph_overhead_custom(128,false),nullptr,true});
        require(ctx,"Context allocation failed");
        q.resize(size_t(p.S)*p.HQ*p.T*p.B); k.resize(q.size()); v.resize(A);
        g.resize(size_t(p.G)*p.H*p.T*p.B); beta.resize(size_t(p.H)*p.T*p.B); initial.resize(D);
        for(int b=0;b<p.B;++b) for(int t=0;t<p.T;++t) {
            for(int h=0;h<p.HQ;++h) {
                double qn=0,kn=0;
                for(int x=0;x<p.S;++x) {
                    size_t i=((size_t(b)*p.T+t)*p.HQ+h)*p.S+x;
                    uint32_t key=(((b*17+t+token_offset)*61+h)*137+x);
                    q[i]=sample(key,p.seed); k[i]=sample(key,p.seed+3719);
                    qn+=double(q[i])*q[i]; kn+=double(k[i])*k[i];
                }
                for(int x=0;x<p.S;++x) {
                    size_t i=((size_t(b)*p.T+t)*p.HQ+h)*p.S+x;
                    q[i]=float(q[i]/std::sqrt(qn)); k[i]=float(k[i]/std::sqrt(kn));
                }
            }
            for(int h=0;h<p.H;++h) {
                size_t i=(size_t(b)*p.T+t)*p.H+h;
                uint32_t key=((b*17+t+token_offset)*61+h);
                beta[i]=0.2f+0.6f*(sample(key,p.seed+813)+1.0f)*0.5f;
                for(int x=0;x<p.S;++x) v[i*p.S+x]=0.3f*sample(key*137+x,p.seed+917);
                for(int x=0;x<p.G;++x) g[i*p.G+x]=-0.01f-0.3f*(sample(key*137+x,p.seed+293)+1.0f)*0.5f;
            }
        }
        for(size_t i=0;i<D;++i) initial[i]=0.1f*sample(uint32_t(i),p.seed+1719);
        if(restored) { require(restored->size()==D,"Wrong restored state size"); initial=*restored; }
        auto make_qkv=[&](const std::vector<float> & values,int heads,int side) {
            size_t hstride=p.S,tstride=size_t(p.S)*heads,bstride=tstride*p.T;
            if(p.layout=="model" && side==2) { tstride=size_t(p.S)*(2*p.HQ+p.H); bstride=tstride*p.T; }
            if(p.layout=="permuted") {
                if(side==0) { tstride=p.S+8; hstride=tstride*(p.T+1); }
                if(side==1) { hstride=p.S+12; tstride=hstride*heads+20; }
                if(side==2) { tstride=p.S+16; hstride=tstride*(p.T+2); }
                bstride=std::max(hstride*heads,tstride*p.T)+24;
            }
            const size_t offset=p.padded_cache?size_t(side+3):(side==2?size_t(2*p.S*p.HQ):0);
            qkv_view_offsets_bytes.push_back(offset*sizeof(float));
            const size_t count=offset+(p.B-1)*bstride+(p.T-1)*tstride+(heads-1)*hstride+p.S+13;
            auto storage=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,count);
            std::vector<float> raw(count,sentinel);
            for(int b=0;b<p.B;++b) for(int t=0;t<p.T;++t) for(int h=0;h<heads;++h) for(int x=0;x<p.S;++x)
                raw[offset+b*bstride+t*tstride+h*hstride+x]=values[((size_t(b)*p.T+t)*heads+h)*p.S+x];
            inputs.push_back({storage,std::move(raw)});
            return ggml_view_4d(ctx,storage,p.S,heads,p.T,p.B,hstride*4,tstride*4,bstride*4,offset*4);
        };
        auto qt=make_qkv(q,p.HQ,0),kt=make_qkv(k,p.HQ,1),vt=make_qkv(v,p.H,2);
        auto gt=ggml_new_tensor_4d(ctx,GGML_TYPE_F32,p.G,p.H,p.T,p.B);
        auto bt=ggml_new_tensor_4d(ctx,GGML_TYPE_F32,1,p.H,p.T,p.B);
        auto st=ggml_new_tensor_4d(ctx,GGML_TYPE_F32,p.S,p.S,p.H,p.B);
        inputs.push_back({gt,g}); inputs.push_back({bt,beta}); inputs.push_back({st,initial});
        out=ggml_gated_delta_net(ctx,qt,kt,vt,gt,bt,st,p.K);
        if(!p.fused) ggml_set_output(out);
        const int written=std::min(p.T,p.K);
        auto tail=ggml_view_3d(ctx,out,D/p.B,p.B,written,D/p.B*4,D*4,A*4);
        cache=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,cache_offset+slot_stride*p.K+19);
        auto destination=ggml_view_3d(ctx,cache,D/p.B,p.B,written,D/p.B*4,slot_stride*4,cache_offset*4);
        auto copy=ggml_cpy(ctx,tail,destination);
        consumer=ggml_sum(ctx,ggml_view_1d(ctx,copy,D,0)); ggml_set_output(consumer);
        auto attn=ggml_view_4d(ctx,out,p.S,p.H,p.T,p.B,p.S*4,p.S*p.H*4,p.S*p.H*p.T*4,0);
        attention_out=ggml_dup(ctx,attn); ggml_set_output(attention_out);
        graph=ggml_new_graph_custom(ctx,128,false);
        ggml_build_forward_expand(graph,consumer); ggml_build_forward_expand(graph,attention_out);
        buffer=ggml_backend_alloc_ctx_tensors(ctx,backend); require(buffer,"Graph buffer allocation failed");
        ggml_backend_t backends[]={backend,cpu_backend};
        scheduler=ggml_backend_sched_new(backends,nullptr,2,128,false,true);require(scheduler,"Scheduler creation failed");
        for(int i=0;i<ggml_graph_n_nodes(graph);++i) ggml_backend_sched_set_tensor_backend(scheduler,ggml_graph_node(graph,i),backend);
        require(ggml_backend_sched_alloc_graph(scheduler,graph),"Scheduler graph allocation failed");
        require(ggml_backend_sched_get_n_splits(scheduler)==1,"Unexpected scheduler split");
        for(int i=0;i<ggml_graph_n_nodes(graph);++i) {
            auto node=ggml_graph_node(graph,i);
            require(ggml_backend_sched_get_tensor_backend(scheduler,node)==backend,"Unexpected CPU graph dispatch");
        }
        for(const auto & input:inputs) ggml_backend_tensor_set(input.first,input.second.data(),0,input.second.size()*4);
        std::vector<float> raw_cache(ggml_nelements(cache),sentinel),raw_out(ggml_nelements(out),sentinel);
        ggml_backend_tensor_set(cache,raw_cache.data(),0,raw_cache.size()*4);
        ggml_backend_tensor_set(out,raw_out.data(),0,raw_out.size()*4);
    }
    ~fixture() { if(scheduler) ggml_backend_sched_free(scheduler); if(buffer) ggml_backend_buffer_free(buffer); if(ctx) ggml_free(ctx); }
    fixture(const fixture &)=delete;
    void compute() {
        require(ggml_backend_sched_graph_compute_async(scheduler,graph)==GGML_STATUS_SUCCESS,"Graph compute failed");
        ggml_backend_sched_synchronize(scheduler);
    }
    result inspect(std::ofstream * evidence, const std::string & id="") {
        result r;
        r.attention.resize(A); r.cache.resize(ggml_nelements(cache)); r.tail.resize(ggml_nelements(out)-A);
        ggml_backend_tensor_get(attention_out,r.attention.data(),0,A*4);
        ggml_backend_tensor_get(cache,r.cache.data(),0,r.cache.size()*4);
        ggml_backend_tensor_get(out,r.tail.data(),A*4,r.tail.size()*4);
        std::vector<float> raw_attention(A);ggml_backend_tensor_get(out,raw_attention.data(),0,A*4);
        require(bits_equal(raw_attention,r.attention),"Attention consumer changed bits");
        for(const auto & input:inputs) {
            std::vector<float> after(input.second.size());ggml_backend_tensor_get(input.first,after.data(),0,after.size()*4);
            require(bits_equal(after,input.second),"Input or padding changed");
        }
        std::vector<double> state(initial.begin(),initial.end());
        std::vector<float> expected_attention(A),expected_state(D*std::min(p.T,p.K));
        for(int t=0;t<p.T;++t) {
            for(int b=0;b<p.B;++b) for(int h=0;h<p.H;++h) for(int row=0;row<p.S;++row) {
                size_t ib=(size_t(b)*p.T+t)*p.H+h, iq=((size_t(b)*p.T+t)*p.HQ+h%p.HQ)*p.S;
                size_t is=((size_t(b)*p.H+h)*p.S+row)*p.S;
                double sk=0;
                for(int x=0;x<p.S;++x) {state[is+x]*=std::exp(double(g[ib*p.G+(p.G==1?0:x)]));sk+=state[is+x]*k[iq+x];}
                double delta=(double(v[ib*p.S+row])-sk)*beta[ib],y=0;
                for(int x=0;x<p.S;++x) {state[is+x]+=double(k[iq+x])*delta;y+=state[is+x]*q[iq+x];}
                expected_attention[ib*p.S+row]=float(y/std::sqrt(double(p.S)));
            }
            int slot=p.K==1?0:p.T-1-t;
            if((p.K>1 || t==p.T-1) && slot<p.K) for(size_t i=0;i<D;++i) expected_state[size_t(slot)*D+i]=float(state[i]);
        }
        double ae=0,ad=0,se=0,sd=0;
        auto error=[&](float a,float expected,double & sum,double & denom) {
            require(std::isfinite(a)&&std::isfinite(expected),"Non-finite output or CPU reference");
            double e=double(a)-expected;sum+=e*e;denom+=double(expected)*expected;r.max_abs=std::max(r.max_abs,std::abs(e));
        };
        for(size_t i=0;i<A;++i) error(r.attention[i],expected_attention[i],ae,ad);
        const int written=std::min(p.T,p.K);
        for(size_t i=0;i<r.cache.size();++i) {
            bool active=i>=cache_offset && i<cache_offset+slot_stride*written && (i-cache_offset)%slot_stride<D;
            if(!active) require(r.cache[i]==sentinel,"Unwritten cache slot or padding changed");
        }
        for(int slot=0;slot<written;++slot) for(size_t i=0;i<D;++i) {
            float value=r.cache[cache_offset+slot_stride*slot+i];error(value,expected_state[D*slot+i],se,sd);
            if(!p.fused) require(std::memcmp(&value,&r.tail[D*slot+i],4)==0,"Unfused snapshot copy changed bits");
        }
        for(size_t i=0;i<r.tail.size();++i) if(p.fused || i>=D*written) require(r.tail[i]==sentinel,"Unwritten GDN tail changed");
        r.attention_nmse=ae/std::max(ad,1e-30);r.state_nmse=se/std::max(sd,1e-30);
        require(r.attention_nmse<1e-10 && r.state_nmse<1e-10 && r.max_abs<2e-5,"CPU recurrence or snapshot reference failed");
        r.attention_values_checked=A;r.state_values_checked=D*written;
        r.final_state.assign(r.cache.begin()+cache_offset,r.cache.begin()+cache_offset+D);
        ggml_backend_tensor_get(consumer,&r.consumer_value,0,4);require(std::isfinite(r.consumer_value),"Non-finite cache consumer");
        if(evidence) {
            auto digest=[&](const std::string & name,std::initializer_list<const std::vector<float> *> parts) {
                CC_SHA256_CTX hash;CC_SHA256_Init(&hash);size_t bytes=0;
                for(const auto * part:parts) {
                    const size_t n=part->size()*sizeof(float);require(n<=UINT32_MAX,"Hash input too large");
                    CC_SHA256_Update(&hash,part->data(),CC_LONG(n));bytes+=n;
                }
                unsigned char value[CC_SHA256_DIGEST_LENGTH];CC_SHA256_Final(value,&hash);
                char hex[2*CC_SHA256_DIGEST_LENGTH+1];
                for(size_t i=0;i<sizeof(value);++i) std::snprintf(hex+2*i,3,"%02x",value[i]);
                *evidence << json({{"id",id+"/"+name},{"bytes",bytes},{"sha256",hex}}).dump() << "\n";
                r.evidence_elements+=bytes/4;
            };
            digest("attention",{&r.attention});digest("cache",{&r.cache});digest("gdn_output",{&raw_attention,&r.tail});
            const std::vector<float> consumed={r.consumer_value};digest("consumer",{&consumed});
            require(bool(*evidence),"Writing full-buffer digest evidence failed");
        }
        return r;
    }
};

static json run_case(ggml_backend_t backend,std::ofstream & evidence,const spec & p,bool perf) {
    const int copies=perf?4:1,samples=perf?512:1;
    const std::string case_id=p.label+"/T"+std::to_string(p.T)+"/"+(p.fused?"fused":"unfused")+"/"+p.layout;
    std::vector<std::unique_ptr<fixture>> pool;
    for(int i=0;i<copies;++i) {spec one=p;one.seed+=i*1013;one.padded_cache=!perf;pool.emplace_back(new fixture(backend,one));}
    for(size_t i=1;i<pool.size();++i) require(!bits_equal(pool[0]->initial,pool[i]->initial),"Repeated input-state fixture");
    const int warmup_minimum_ms=perf?500:0;
    size_t warmup_graphs=0;
    double warmup_elapsed_ms=0;
    if(perf) {
        // Compile and initialize every graph before the sustained compute warmup.
        for(auto & f:pool) f->compute();
        const auto start=std::chrono::steady_clock::now();
        do {
            pool[warmup_graphs%pool.size()]->compute();++warmup_graphs;
            warmup_elapsed_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
        } while(warmup_elapsed_ms<warmup_minimum_ms || warmup_graphs<pool.size());
    }
    std::vector<double> times;times.reserve(samples);
    for(int i=0;i<samples;++i) {
        auto & f=*pool[size_t(i)%pool.size()];
        const auto start=std::chrono::steady_clock::now();f.compute();
        times.push_back(std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count());
    }
    size_t elements=0,attention_values_checked=0,state_values_checked=0;double attention_nmse=0,state_nmse=0,max_abs=0;
    auto collect=[&](const result & r) {elements+=r.evidence_elements;attention_values_checked+=r.attention_values_checked;state_values_checked+=r.state_values_checked;attention_nmse=std::max(attention_nmse,r.attention_nmse);state_nmse=std::max(state_nmse,r.state_nmse);max_abs=std::max(max_abs,r.max_abs);};
    std::vector<int> restored_prefixes,unavailable_prefixes;
    for(auto & owned:pool) {
        auto & f=*owned;auto actual=f.inspect(perf?nullptr:&evidence,case_id+"/main");collect(actual);
        if(perf || p.label!="target") continue;
        for(int accepted=0;accepted<=p.T;++accepted) {
            const int slot=p.T-accepted;
            if(accepted>0 && slot>=p.K) {unavailable_prefixes.push_back(accepted);continue;}
            std::vector<float> restore=f.initial;
            if(accepted>0) restore.assign(actual.cache.begin()+f.cache_offset+slot*f.slot_stride,
                                          actual.cache.begin()+f.cache_offset+slot*f.slot_stride+f.D);
            std::vector<float> prefix_state=f.initial;
            if(accepted>0) {
                spec prefix=p;prefix.T=accepted;
                fixture reference(backend,prefix);reference.compute();auto checked=reference.inspect(&evidence,case_id+"/prefix/"+std::to_string(accepted));collect(checked);
                prefix_state=std::move(checked.final_state);
            }
            require(bits_equal(restore,prefix_state),"Rollback snapshot differs from independently computed prefix");
            spec next=p;next.T=1;
            fixture from_slot(backend,next,accepted,&restore),from_prefix(backend,next,accepted,&prefix_state);
            from_slot.compute();from_prefix.compute();auto a=from_slot.inspect(&evidence,case_id+"/slot-next/"+std::to_string(accepted)),b=from_prefix.inspect(&evidence,case_id+"/prefix-next/"+std::to_string(accepted));collect(a);collect(b);
            require(bits_equal(a.attention,b.attention) && bits_equal(a.cache,b.cache) && bits_equal(a.tail,b.tail) && std::memcmp(&a.consumer_value,&b.consumer_value,4)==0,"Rollback continuation changed full buffers");
            restored_prefixes.push_back(accepted);
        }
    }
    auto sorted_times=times;std::sort(sorted_times.begin(),sorted_times.end());
    const double median_us=(sorted_times[(sorted_times.size()-1)/2]+sorted_times[sorted_times.size()/2])*0.5;
    return {{"label",p.label},{"S",p.S},{"H",p.H},{"HQ",p.HQ},{"T",p.T},{"B",p.B},{"K",p.K},{"G",p.G},
        {"fused",p.fused},{"layout",p.layout},{"samples",samples},{"distinct_state_buffers",copies},
        {"geometry",{{"padded_cache",pool[0]->p.padded_cache},{"qkv_view_offsets_bytes",pool[0]->qkv_view_offsets_bytes},
                     {"cache_view_offset_bytes",pool[0]->cache_offset*sizeof(float)},{"cache_slot_stride_floats",pool[0]->slot_stride}}},
        {"warmup_minimum_ms",warmup_minimum_ms},{"warmup_elapsed_ms",warmup_elapsed_ms},{"warmup_graphs",warmup_graphs},
        {"wall_samples_us_per_graph_sync",times},{"wall_us_per_graph_sync",median_us},{"attention_nmse",attention_nmse},{"state_nmse",state_nmse},{"max_absolute_error",max_abs},
        {"elements",elements},{"attention_values_checked",attention_values_checked},{"state_values_checked",state_values_checked},{"continuation_pairs",restored_prefixes.size()},{"scheduler_splits",1},{"all_nodes_metal",true},{"inputs_preserved",true},{"unwritten_slots_preserved",true},{"rollback_prefixes",restored_prefixes},{"unavailable_prefixes",unavailable_prefixes}};
}

int main(int argc,char ** argv) {
    std::setvbuf(stdout,nullptr,_IOLBF,0);
    try {
        require(argc==3,"Usage: gdn-probe check|perf outputs.jsonl");
        const std::string mode=argv[1];require(mode=="check"||mode=="perf","Unknown mode");
        std::ofstream evidence(argv[2],std::ios::binary);require(bool(evidence),"Evidence file unavailable");
        ggml_backend_load_all();cpu_backend=ggml_backend_init_by_name("CPU",nullptr);require(cpu_backend,"CPU fallback backend unavailable");auto backend=ggml_backend_init_by_name("MTL0",nullptr);require(backend,"Metal unavailable");
        int count=0;size_t elements=0;
        auto run=[&](const spec & p) {
            auto result=run_case(backend,evidence,p,mode=="perf");elements+=result.at("elements").get<size_t>();
            printf("M5_GDN_CASE %s\n",result.dump().c_str());++count;
        };
        for(int tokens:{1,2,3,4,5}) for(bool fused:{true,false}) for(const std::string & layout:mode=="check"?std::vector<std::string>{"model","permuted"}:std::vector<std::string>{"model"}) {
            spec p;p.T=tokens;p.fused=fused;p.layout=layout;run(p);
        }
        if(mode=="check") for(const std::string & label:{"K1","T6","H32","B2","S64","G128"}) for(bool fused:{true,false}) {
            spec p;p.label=label;p.fused=fused;
            if(label=="K1") p.K=1;if(label=="T6") p.T=6;if(label=="H32") p.H=32;
            if(label=="B2") p.B=2;if(label=="S64") p.S=64;if(label=="G128") p.G=128;
            run(p);
        }
        printf("M5_GDN_DONE %s\n",json({{"mode",mode},{"cases",count},{"elements",elements},{"sync_included",true},{"callbacks_used",false},{"evidence_format","sha256-buffer-manifest-v1"}}).dump().c_str());
        ggml_backend_free(backend);ggml_backend_free(cpu_backend);return 0;
    } catch(const std::exception & e) {fprintf(stderr,"M5_GDN_ERROR %s\n",e.what());return 1;}
}
