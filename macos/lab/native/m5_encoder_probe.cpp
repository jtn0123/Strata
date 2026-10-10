#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-alloc.h"
#include "ggml-metal.h"
#include <nlohmann/json.hpp>
#include <CommonCrypto/CommonDigest.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

using json=nlohmann::json;
using getter_t=bool (*)(ggml_backend_t,int *,int);
static void require(bool ok,const char * message) {if(!ok) throw std::runtime_error(message);}
static constexpr int width=256,padding=13;
static constexpr float sentinel=12345.0f;

static std::array<int,8> encoding_info(ggml_backend_t backend,getter_t getter) {
    std::array<int,8> values{};require(getter(backend,values.data(),8),"Encoding getter failed");return values;
}
static json digest(const std::string & id,const std::vector<float> & values) {
    unsigned char hash[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(values.data(),CC_LONG(values.size()*4),hash);
    char hex[65];for(size_t i=0;i<sizeof(hash);++i) std::snprintf(hex+2*i,3,"%02x",hash[i]);
    return {{"id",id},{"bytes",values.size()*4},{"sha256",hex}};
}

static json run_case(ggml_backend_t metal,ggml_backend_t cpu,getter_t getter,int expected,
                     int steps,bool alias,std::ofstream & evidence) {
    auto ctx=ggml_init({ggml_tensor_overhead()*4096+ggml_graph_overhead_custom(4096,false),nullptr,true});
    require(ctx,"Context allocation failed");
    auto graph=ggml_new_graph_custom(ctx,4096,false);
    auto storage=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,width+2*padding);
    auto initial=ggml_view_1d(ctx,storage,width,padding*4);
    auto cur=initial;
    std::vector<ggml_tensor *> increments;
    for(int step=0;step<steps;++step) {
        auto delta=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,width);increments.push_back(delta);
        cur=ggml_add(ctx,cur,delta);
        if(alias) cur=ggml_cpy(ctx,cur,ggml_view_1d(ctx,storage,width,padding*4));
    }
    // A distinct output avoids making the last cache CPY a graph output.
    auto output=ggml_dup(ctx,cur);ggml_set_output(output);ggml_build_forward_expand(graph,output);
    auto buffer=ggml_backend_alloc_ctx_tensors(ctx,metal);require(buffer,"Buffer allocation failed");
    ggml_backend_t backends[]={metal,cpu};
    auto sched=ggml_backend_sched_new(backends,nullptr,2,4096,false,true);require(sched,"Scheduler creation failed");
    for(int i=0;i<ggml_graph_n_nodes(graph);++i) ggml_backend_sched_set_tensor_backend(sched,ggml_graph_node(graph,i),metal);
    require(ggml_backend_sched_alloc_graph(sched,graph),"Scheduler allocation failed");
    require(ggml_backend_sched_get_n_splits(sched)==1,"Unexpected scheduler split");
    for(int i=0;i<ggml_graph_n_nodes(graph);++i)
        require(ggml_backend_sched_get_tensor_backend(sched,ggml_graph_node(graph,i))==metal,"Unexpected CPU execution");
    std::vector<float> raw(width+2*padding,sentinel),reference(width),delta(width);
    for(int i=0;i<width;++i) raw[padding+i]=reference[i]=float(i%127-63)/4096.0f;
    ggml_backend_tensor_set(storage,raw.data(),0,raw.size()*4);
    for(int step=0;step<steps;++step) {
        for(int i=0;i<width;++i) {delta[i]=float(1+(step*13+i*7)%31)/4096.0f;reference[i]+=delta[i];}
        ggml_backend_tensor_set(increments[step],delta.data(),0,delta.size()*4);
    }
    require(ggml_backend_sched_graph_compute_async(sched,graph)==GGML_STATUS_SUCCESS,"Graph failed");
    ggml_backend_sched_synchronize(sched);
    auto values=encoding_info(metal,getter);
    const int nodes=ggml_graph_n_nodes(graph),main=expected==0?nodes:std::min(nodes,std::max(64,int(0.1*nodes)));
    const int remainder=nodes-main,per=expected?((remainder+expected-1)/expected):0;
    require(values[0]==expected && values[1]==main && values[2]==remainder && values[3]==per,"Wrong effective partition plan");
    require(values[4]==1 && values[6]==1 && values[7]==1,"Fusion/concurrency/optimizer unexpectedly disabled");
    std::vector<std::array<int,2>> partitions={{0,main}};
    for(int worker=0;worker<expected;++worker) partitions.push_back({main+worker*per,main+std::min(remainder,(worker+1)*per)});
    require(partitions.back()[1]==nodes,"Partition does not cover complete graph");
    for(size_t i=1;i<partitions.size();++i) require(partitions[i-1][1]==partitions[i][0],"Partition gap or overlap");
    std::unordered_map<ggml_tensor *,int> indices;
    for(int i=0;i<nodes;++i) indices[ggml_graph_node(graph,i)]=i;
    int crossed_boundaries=0;
    for(size_t part=1;part<partitions.size();++part) {
        const int boundary=partitions[part][0];if(boundary==nodes) continue;
        bool crossed=false;
        for(int i=boundary;i<nodes;++i) for(auto src:ggml_graph_node(graph,i)->src) {
            auto found=indices.find(src);
            if(found!=indices.end() && found->second<boundary) crossed=true;
        }
        require(crossed,"No dependency crosses active command-buffer boundary");++crossed_boundaries;
    }
    std::vector<float> actual(width),after(raw.size());
    ggml_backend_tensor_get(output,actual.data(),0,actual.size()*4);
    ggml_backend_tensor_get(storage,after.data(),0,after.size()*4);
    require(std::memcmp(actual.data(),reference.data(),width*4)==0,"CPU dyadic reference differs in output bits");
    for(size_t i=0;i<after.size();++i) {
        const float wanted=alias && i>=padding && i<padding+width?reference[i-padding]:raw[i];
        require(std::isfinite(after[i]) && std::memcmp(&after[i],&wanted,4)==0,"Cache state or guard padding changed");
    }
    for(int step=0;step<steps;++step) {
        ggml_backend_tensor_get(increments[step],delta.data(),0,delta.size()*4);
        for(int i=0;i<width;++i) require(delta[i]==float(1+(step*13+i*7)%31)/4096.0f,"Read-only increment changed");
    }
    const std::string id=std::string(alias?"alias":"add")+"/"+std::to_string(steps);
    evidence<<digest(id+"/output",actual).dump()<<"\n"<<digest(id+"/storage",after).dump()<<"\n";
    require(bool(evidence),"Evidence write failed");
    json result={{"kind",alias?"alias":"add"},{"steps",steps},{"raw_nodes",nodes},{"plan",values},
        {"partitions",partitions},{"crossed_boundaries",crossed_boundaries},{"scheduler_splits",1},{"all_nodes_metal",true},
        {"cpu_bit_exact",true},{"inputs_preserved",true},{"padding_preserved",true},{"digest_buffers",2},{"checked_values",actual.size()+after.size()}};
    ggml_backend_sched_free(sched);ggml_backend_buffer_free(buffer);ggml_free(ctx);return result;
}

int main(int argc,char ** argv) {
    std::setvbuf(stdout,nullptr,_IOLBF,0);
    try {
        require(argc==4,"Usage: encoder-probe legacy|registry expected_n_cb outputs.jsonl");
        const std::string constructor=argv[1];require(constructor=="legacy"||constructor=="registry","Unknown constructor");
        require(std::strlen(argv[2])==1 && argv[2][0]>='0' && argv[2][0]<='2',"Wrong expected encoder count");
        const int expected=argv[2][0]-'0';std::ofstream evidence(argv[3]);require(bool(evidence),"Evidence file unavailable");
        ggml_backend_load_all();
        auto metal=constructor=="legacy"?ggml_backend_metal_init():ggml_backend_init_by_name("MTL0",nullptr);
        auto cpu=ggml_backend_init_by_name("CPU",nullptr);require(metal&&cpu,"Backends unavailable");
        auto reg=ggml_backend_dev_backend_reg(ggml_backend_get_device(metal));
        auto getter=(getter_t)ggml_backend_reg_get_proc_address(reg,"ggml_backend_metal_m5_lab_get_encoding_info");
        require(getter,"Encoding getter unavailable");
        auto initial=encoding_info(metal,getter);require(initial[0]==expected,"Constructor ignored encoder setting");
        require(!getter(metal,nullptr,8) && !getter(metal,initial.data(),7),"Getter accepted invalid output buffer");
        printf("M5_ENCODERS_START %s\n",json({{"constructor",constructor},{"effective_n_cb",expected},{"plan",initial}}).dump().c_str());
        int count=0;
        for(bool alias:{false,true}) for(int steps:alias?std::vector<int>{21,43,217}:std::vector<int>{61,62,63,64,128,648}) {
            printf("M5_ENCODERS_CASE %s\n",run_case(metal,cpu,getter,expected,steps,alias,evidence).dump().c_str());++count;
        }
        printf("M5_ENCODERS_DONE %s\n",json({{"constructor",constructor},{"cases",count},{"cpu_bit_exact",true},{"timings_measured",false}}).dump().c_str());
        ggml_backend_free(metal);ggml_backend_free(cpu);return 0;
    } catch(const std::exception & error) {fprintf(stderr,"M5_ENCODERS_ERROR %s\n",error.what());return 1;}
}
