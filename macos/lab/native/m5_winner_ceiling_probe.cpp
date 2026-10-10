// Adapted from m5_head_probe.cpp for an ideal consumer-removal screen.
#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-alloc.h"
#include <nlohmann/json.hpp>
#include <CommonCrypto/CommonDigest.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using json=nlohmann::json;
using clock_type=std::chrono::steady_clock;
static constexpr int K=2560,M=248320;
static bool floor_only=false;
static void require(bool ok,const char * message){if(!ok)throw std::runtime_error(message);}
static double elapsed_us(clock_type::time_point start){return std::chrono::duration<double,std::micro>(clock_type::now()-start).count();}
static uint32_t next(uint32_t & s){s^=s<<13;s^=s>>17;s^=s<<5;return s;}
static std::string hash_bytes(const void * data,size_t bytes){
    unsigned char hash[CC_SHA256_DIGEST_LENGTH];require(bytes<=UINT32_MAX,"Digest input too large");
    CC_SHA256(data,CC_LONG(bytes),hash);char result[65];
    for(size_t i=0;i<sizeof(hash);++i)std::snprintf(result+2*i,3,"%02x",hash[i]);return result;
}
static std::vector<float> read_f32(ggml_tensor * t){
    require(ggml_is_contiguous(t),"Noncontiguous output evidence");std::vector<float> out(ggml_nelements(t));
    ggml_backend_tensor_get(t,out.data(),0,out.size()*4);return out;
}

struct weights {
    ggml_context * ctx=nullptr;ggml_backend_buffer_t buffer=nullptr;ggml_tensor * tensor=nullptr;
    std::vector<uint8_t> packed;std::string hash;int storage_k=K;
    weights(ggml_backend_t metal,bool padded){
        storage_k=K+(padded?256:0);ctx=ggml_init({ggml_tensor_overhead()*8,nullptr,true});require(ctx,"Weight context failed");
        tensor=ggml_new_tensor_2d(ctx,GGML_TYPE_Q5_K,storage_k,M);ggml_set_name(tensor,"output.weight");
        require(ggml_type_size(GGML_TYPE_Q5_K)==176 && ggml_blck_size(GGML_TYPE_Q5_K)==256,"Q5_K ABI differs");
        packed.resize(ggml_nbytes(tensor));uint32_t seed=0x62e95017;
        // Build valid packed blocks directly; no expanded float matrix or model file.
        for(int row=0;row<M;++row)for(int block=0;block<storage_k/256;++block){
            auto * p=packed.data()+size_t(row)*tensor->nb[1]+block*176;
            for(int i=4;i<176;++i)p[i]=uint8_t(next(seed));
            float d=std::ldexp(float(64+(next(seed)&63)),-13);
            float dmin=std::ldexp(float(next(seed)&31),-13);
            if(row<20){
                // Eight strictly higher rows and twelve equal cutoff rows for the ones fixture.
                d=row<8?float(48-row)/1024.0f:32.0f/1024.0f;dmin=0;
                std::memset(p+4,255,172);
            }
            const ggml_fp16_t h=ggml_fp32_to_fp16(d),hm=ggml_fp32_to_fp16(dmin);
            std::memcpy(p,&h,2);std::memcpy(p+2,&hm,2);
        }
        hash=hash_bytes(packed.data(),packed.size());buffer=ggml_backend_alloc_ctx_tensors(ctx,metal);require(buffer,"Weight buffer failed");
        ggml_backend_buffer_set_usage(buffer,GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
        ggml_backend_tensor_set(tensor,packed.data(),0,packed.size());
    }
    void preserved(){
        std::vector<uint8_t> chunk(16*1024*1024);CC_SHA256_CTX digest;CC_SHA256_Init(&digest);
        for(size_t offset=0;offset<packed.size();offset+=chunk.size()){
            const size_t n=std::min(chunk.size(),packed.size()-offset);
            ggml_backend_tensor_get(tensor,chunk.data(),offset,n);
            require(std::memcmp(chunk.data(),packed.data()+offset,n)==0,"Packed weight bytes changed");
            CC_SHA256_Update(&digest,chunk.data(),CC_LONG(n));
        }
        unsigned char raw[32];CC_SHA256_Final(raw,&digest);char hex[65];
        for(int i=0;i<32;++i)std::snprintf(hex+2*i,3,"%02x",raw[i]);require(hash==hex,"Weight digest differs");
        require(hash_bytes(packed.data(),packed.size())==hash,"Host packed weights changed");
    }
    ~weights(){if(buffer)ggml_backend_buffer_free(buffer);if(ctx)ggml_free(ctx);}
};

struct case_spec {std::string id;int rows=1,k=K,m=M;bool padded=false;};
static std::vector<case_spec> inventory(bool perf){
    if(perf)return {{"mixed"},{"alternating"}};
    return {{"mixed"},{"alternating"},{"one-hot"},{"zeros"},{"wide"},{"cutoff-ties"},{"dense-view"},
        {"rows2",2},{"rows4",4},{"near-k",1,2304},{"near-m",1,K,M-2},{"input-padded"},{"input-offset"},
        {"weight-view"},{"wrong-name"},{"weight-padded",1,K,M,true}};
}
static bool eligible(const case_spec & c){
    return c.rows==1&&c.k==K&&c.m==M&&!c.padded&&c.id!="input-padded"&&c.id!="input-offset"&&c.id!="weight-view"&&c.id!="wrong-name";
}

static json run_case(ggml_backend_t metal,ggml_backend_t cpu,weights & w,const case_spec & spec,bool perf,std::ofstream & evidence){
    printf("M5_WINNER_CEILING_CASE_BEGIN %s\n",json({{"id",spec.id},{"eligible",eligible(spec)}}).dump().c_str());
    const int rows=spec.rows,k=spec.k,m=spec.m,offset=spec.id=="input-offset"?1:0;
    const int stride=k+((spec.id=="input-padded"||offset)?4:0);
    auto ctx=ggml_init({ggml_tensor_overhead()*256+ggml_graph_overhead_custom(256,false),nullptr,true});require(ctx,"Graph context failed");
    auto graph=ggml_new_graph_custom(ctx,256,false);
    auto input=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,stride,rows);ggml_set_input(input);ggml_set_output(input);
    ggml_tensor * x=input;
    if(stride!=k||offset||spec.id=="dense-view")x=ggml_view_2d(ctx,input,k,rows,stride*4,offset*4);
    ggml_set_name(x,"result_norm");
    auto wt=w.tensor;
    if(spec.padded||k!=K||m!=M||spec.id=="weight-view")wt=ggml_view_2d(ctx,w.tensor,k,m,w.tensor->nb[1],0);
    ggml_set_name(wt,"output.weight");
    auto logits=ggml_mul_mat(ctx,wt,x);ggml_set_name(logits,spec.id=="wrong-name"?"other_output":"result_output");
    ggml_set_output(logits);ggml_build_forward_expand(graph,logits);
    std::vector<ggml_tensor *> selected,values;
    for(int r=0;!floor_only&&r<rows;++r){
        auto row=ggml_view_1d(ctx,logits,m,size_t(r)*m*4);
        auto ids=ggml_top_k(ctx,row,10);auto val=ggml_get_rows(ctx,ggml_reshape_2d(ctx,row,1,m),ids);
        ggml_set_output(ids);ggml_set_output(val);ggml_build_forward_expand(graph,val);selected.push_back(ids);values.push_back(val);
    }
    ggml_backend_t backends[]={metal,cpu};auto sched=ggml_backend_sched_new(backends,nullptr,2,256,false,true);require(sched,"Scheduler unavailable");
    ggml_backend_sched_set_tensor_backend(sched,input,metal);
    for(int i=0;i<ggml_graph_n_nodes(graph);++i)ggml_backend_sched_set_tensor_backend(sched,ggml_graph_node(graph,i),metal);
    require(ggml_backend_sched_alloc_graph(sched,graph),"Scheduler allocation failed");
    require(ggml_backend_sched_get_n_splits(sched)==1,"Unexpected scheduler split");
    auto check_storage=[&](ggml_tensor * t){auto * base=t->view_src?t->view_src:t;require(base->buffer&&
        ggml_backend_buffer_get_type(base->buffer)==ggml_backend_get_default_buffer_type(metal),"Storage is not Metal");};
    for(int i=0;i<ggml_graph_n_nodes(graph);++i){auto * node=ggml_graph_node(graph,i);
        require(ggml_backend_sched_get_tensor_backend(sched,node)==metal,"Unexpected CPU compute node");check_storage(node);
        for(auto * src:node->src)if(src)check_storage(src);
    }
    std::vector<float> raw(size_t(stride)*rows,12345.0f);uint32_t seed=0x52345931;
    for(int r=0;r<rows;++r){
        double mean=0;for(int i=0;i<k;++i){float v=float(int32_t(next(seed))%100000)/100000.0f;raw[r*stride+offset+i]=v;mean+=v;}
        for(int i=0;i<k;++i){auto & v=raw[r*stride+offset+i];v-=float(mean/k);
            if(spec.id=="alternating")v=(i%2?-1.0f:1.0f)*1.00000011920928955f;
            if(spec.id=="one-hot")v=(i==255||i==256||i==k-1)?1.0f:0.0f;
            if(spec.id=="zeros")v=0.0f;
            if(spec.id=="wide")v=std::ldexp(v,i%17-8);
            if(spec.id=="cutoff-ties")v=1.0f;
        }
    }
    const auto input_hash=hash_bytes(raw.data(),raw.size()*4);ggml_backend_tensor_set(input,raw.data(),0,raw.size()*4);
    auto compute=[&](){require(ggml_backend_sched_graph_compute_async(sched,graph)==GGML_STATUS_SUCCESS,"Graph compute failed");ggml_backend_sched_synchronize(sched);};
    std::vector<double> blocks_us,per_iter;std::vector<int> iterations;double warmup_us=0;int warmup_iterations=0;
    if(perf){
        compute(); // Prime lazy pipelines outside the sustained warmup clock.
        auto warm=clock_type::now();do{compute();++warmup_iterations;}while(elapsed_us(warm)<500000);warmup_us=elapsed_us(warm);
        for(int block=0;block<7;++block){auto begin=clock_type::now();int n=0;double us;
            do{compute();++n;us=elapsed_us(begin);}while(us<100000||n<8);
            blocks_us.push_back(us);iterations.push_back(n);per_iter.push_back(us/n);
        }
    }else compute();
    auto actual=read_f32(logits);require(actual.size()==size_t(m)*rows,"Logit count differs");
    double max_error=0,max_bound_ratio=0,error=0,energy=0;size_t checked=0;
    if(!perf){
        std::vector<float> dequant(k);auto to_float=ggml_get_type_traits(GGML_TYPE_Q5_K)->to_float;require(to_float,"CPU dequantizer unavailable");
        for(int row=0;row<m;++row){
            to_float(w.packed.data()+size_t(row)*w.tensor->nb[1],dequant.data(),k);
            for(int r=0;r<rows;++r){double total=0,absolute=0;
                for(int i=0;i<k;++i){const double v=double(dequant[i])*raw[r*stride+offset+i];total+=v;absolute+=std::abs(v);}
                const double d=double(actual[size_t(r)*m+row])-total;
                require(std::isfinite(d),"Non-finite CPU reference/logit");
                const double ratio=std::abs(d)/std::max(1.0,absolute);
                max_error=std::max(max_error,std::abs(d));max_bound_ratio=std::max(max_bound_ratio,ratio);error+=d*d;energy+=total*total;++checked;
            }
        }
        // Few-row fallback may use the existing MMA precision path. Canonical
        // candidate reference is stricter; candidate-vs-stock remains bit exact.
        require(max_bound_ratio<(rows==1?5e-6:2e-4),"Streaming CPU reference error exceeds bound");
    }
    json consumers=json::array();
    for(int r=0;!floor_only&&r<rows;++r){
        std::vector<int32_t> ids(10);ggml_backend_tensor_get(selected[r],ids.data(),0,40);auto vals=read_f32(values[r]);
        require(vals.size()==10&&std::set<int32_t>(ids.begin(),ids.end()).size()==10,"Top-k duplicated/missing IDs");
        std::vector<float> sorted(actual.begin()+size_t(r)*m,actual.begin()+size_t(r+1)*m);
        for(float v:sorted)require(std::isfinite(v),"Nonfinite logit");
        // Match Metal's signed-float radix ordering, including signed zero.
        auto key=[](float v){uint32_t b;std::memcpy(&b,&v,4);return b&0x80000000u?~b:b|0x80000000u;};
        std::nth_element(sorted.begin(),sorted.begin()+9,sorted.end(),[&](float a,float b){return key(a)>key(b);});
        const uint32_t threshold=key(sorted[9]);int above=0,ties=0,chosen_above=0;
        for(int i=0;i<m;++i){const auto v=key(actual[size_t(r)*m+i]);above+=v>threshold;ties+=v==threshold;}
        for(int j=0;j<10;++j){require(ids[j]>=0&&ids[j]<m,"Top-k ID out of range");const float v=actual[size_t(r)*m+ids[j]];
            require(std::memcmp(&v,&vals[j],4)==0,"Gathered logit differs from selected full logit");
            require(key(v)>=threshold,"Top-k selected below threshold");chosen_above+=key(v)>threshold;
        }
        require(chosen_above==above,"Top-k omitted strictly greater logit");
        consumers.push_back({{"ids",ids},{"values",vals},{"above_cutoff",above},{"cutoff_ties",ties},{"tie_safe",true}});
    }
    auto after=read_f32(input);require(after.size()==raw.size()&&std::memcmp(after.data(),raw.data(),raw.size()*4)==0,"Input/padding changed");
    require(input_hash==hash_bytes(after.data(),after.size()*4),"Input digest changed");
    const auto output_hash=hash_bytes(actual.data(),actual.size()*4);
    evidence<<json({{"id",spec.id},{"elements",actual.size()},{"sha256",output_hash}}).dump()<<'\n';
    auto sorted_times=per_iter;std::sort(sorted_times.begin(),sorted_times.end());
    const size_t graph_bytes=ggml_backend_sched_get_buffer_size(sched,metal);
    const size_t bound=2*w.packed.size()+graph_bytes+64*1024*1024;
    require(bound<3ull*1024*1024*1024,"Probe allocation budget exceeded");
    json result={{"id",spec.id},{"rows",rows},{"k",k},{"m",m},{"eligible",eligible(spec)},
        {"elements",actual.size()},{"output_sha256",output_hash},{"input_sha256",input_hash},{"weight_sha256",w.hash},
        {"inputs_preserved",true},{"all_nodes_metal",true},{"scheduler_splits",1},{"cpu_compute_nodes",0},
        {"cpu_reference_values",checked},{"max_absolute_error",max_error},{"max_bound_ratio",max_bound_ratio},
        {"cpu_nmse",error/std::max(energy,1e-30)},{"consumers",consumers},{"consumer_chain",floor_only?"head-only":"head-top_k10-gather"},
        {"pipeline_primed",perf},{"warmup_us",warmup_us},{"warmup_iterations",warmup_iterations},{"block_us",blocks_us},{"block_iterations",iterations},
        {"block_us_per_iteration",per_iter},{"median_us",perf?sorted_times[sorted_times.size()/2]:0},
        {"graph_buffer_bytes",graph_bytes},{"allocation_bound_bytes",bound}};
    ggml_backend_sched_free(sched);ggml_free(ctx);return result;
}

int main(int argc,char ** argv){
    std::setvbuf(stdout,nullptr,_IOLBF,0);
    try{
        require(argc==4,"Usage: winner-ceiling check|perf outputs.jsonl control|head-floor");
        const std::string scope=argv[3];require(scope=="control"||scope=="head-floor","Unknown scope");floor_only=scope=="head-floor";
        const std::string mode=argv[1];require(mode=="check"||mode=="perf","Unknown mode");
        const bool perf=mode=="perf";std::ofstream evidence(argv[2]);require(bool(evidence),"Evidence file unavailable");
        ggml_backend_load_all();auto metal=ggml_backend_init_by_name("MTL0",nullptr);auto cpu=ggml_backend_init_by_type(GGML_BACKEND_DEVICE_TYPE_CPU,nullptr);
        require(metal&&cpu,"Backends unavailable");int count=0;json weight_receipts=json::array();
        for(bool padded:{false,true}){
            if(perf&&padded)continue;
            weights w(metal,padded);
            for(const auto & c:inventory(perf))if(c.padded==padded){
                printf("M5_WINNER_CEILING_CASE %s\n",run_case(metal,cpu,w,c,perf,evidence).dump().c_str());++count;
            }
            w.preserved();weight_receipts.push_back({{"padded",padded},{"bytes",w.packed.size()},{"sha256",w.hash},{"preserved",true}});
        }
        require(bool(evidence),"Evidence write failed");
        printf("M5_WINNER_CEILING_DONE %s\n",json({{"mode",mode},{"scope",scope},{"cases",count},{"weights",weight_receipts},{"weights_preserved",true},
            {"max_probe_bytes",3ull*1024*1024*1024},{"expanded_weight_cache",false},{"models_loaded",false}}).dump().c_str());
        ggml_backend_free(cpu);ggml_backend_free(metal);return 0;
    }catch(const std::exception & e){fprintf(stderr,"M5_WINNER_CEILING_ERROR %s\n",e.what());return 1;}
}
