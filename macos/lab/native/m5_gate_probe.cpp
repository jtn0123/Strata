#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-alloc.h"
#include <nlohmann/json.hpp>
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
void require(bool ok, const char * message) { if (!ok) throw std::runtime_error(message); }

struct weights {
    ggml_tensor * tensor;
    int k, m;
    std::vector<uint8_t> packed;
};

weights make_weights(ggml_context * ctx, int k, int m, uint32_t seed, bool padded=false) {
    weights w{ggml_new_tensor_3d(ctx, GGML_TYPE_Q2_0, k, m+int(padded), 512), k, m, {}};
    w.packed.resize(ggml_nbytes(w.tensor));
    std::vector<float> chunk(64*k);
    const size_t row_bytes=ggml_row_size(GGML_TYPE_Q2_0,k);
    const float scale=1.0f/std::sqrt(float(k));
    for (int row=0; row<512*(m+int(padded)); row+=64) {
        int n=std::min(64,512*(m+int(padded))-row);
        for (int i=0; i<n*k; ++i) {
            seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;
            chunk[i]=float(int32_t(seed)%100000)/100000.0f*scale;
        }
        require(ggml_quantize_chunk(GGML_TYPE_Q2_0,chunk.data(),w.packed.data()+row*row_bytes,
                                   0,n,k,nullptr)==n*row_bytes,"Quantized weight size differs");
    }
    return w;
}

std::vector<int> routing(const json & fixture, int rows, const std::string & route, int copy) {
    std::vector<int> result(10*rows);
    if (route=="real") {
        const auto & ids=fixture.at("routes").at(std::to_string(rows)).at(copy%8).at("ids");
        for (int r=0;r<rows;++r) for(int e=0;e<10;++e) result[r*10+e]=ids.at(r).at(e);
    } else {
        for(int r=0;r<rows;++r) for(int e=0;e<10;++e) {
            if(route=="distinct") result[r*10+e]=(copy*61+r*10+e)%512;
            else if(route=="shared") result[r*10+e]=(copy*61+e)%512;
            else if(route=="duplicate") result[r*10+e]=(copy*61+511)%512;
            else if(route=="mixed") result[r*10+e]=e<5?(copy*61+e)%512:(copy*61+r*10+e)%512;
            else throw std::runtime_error("Unknown routing fixture");
        }
    }
    return result;
}


struct check_stats {
    double error=0, energy=0, max_absolute=0, max_scaled=0;
    size_t values=0;
    void add(double actual, double reference) {
        const double d=actual-reference;
        require(std::isfinite(d), "Non-finite output or CPU reference");
        error+=d*d;energy+=reference*reference;
        max_absolute=std::max(max_absolute,std::abs(d));
        max_scaled=std::max(max_scaled,std::abs(d)/std::max(1.0,std::abs(reference)));
        ++values;
    }
    double nmse() const {return error/std::max(energy,1e-30);}
};

std::vector<float> read_f32(ggml_tensor * t) {
    require(ggml_is_contiguous(t),"Evidence output is not contiguous");
    std::vector<float> out(ggml_nelements(t));
    ggml_backend_tensor_get(t,out.data(),0,out.size()*sizeof(float));return out;
}

std::vector<double> reference_projection(const weights & w, const std::vector<float> & x,
                                        const std::vector<int> & ids, int rows, int input_slots) {
    std::vector<double> result(size_t(w.m)*10*rows);
    std::vector<float> dequant(w.k);
    for(int r=0;r<rows;++r) for(int e=0;e<10;++e) for(int col=0;col<w.m;++col) {
        const uint8_t * packed=w.packed.data()+ids[r*10+e]*w.tensor->nb[2]+col*w.tensor->nb[1];
        ggml_get_type_traits(GGML_TYPE_Q2_0)->to_float(packed,dequant.data(),w.k);
        const float * values=x.data()+(r*input_slots+e%input_slots)*w.k;
        double total=0;for(int k=0;k<w.k;++k) total+=double(dequant[k])*values[k];
        result[(r*10+e)*w.m+col]=total;
    }
    return result;
}

bool eligible(int rows,const std::string & layout) {
    if(rows!=4&&rows!=5)return false;
    return layout=="plain"||layout=="chain"||layout=="ids-contiguous"||layout=="ids-offset"||
           layout=="reversed"||layout=="wide"||layout=="cancel";
}

struct block_case {
    weights * gate_w;weights * up_w;weights * down_w;
    ggml_tensor * x;ggml_tensor * gate;ggml_tensor * up;
    ggml_tensor * activated;ggml_tensor * down;ggml_tensor * bridge;ggml_tensor * extra;
    std::vector<int> ids, up_ids;
};

json run_case(ggml_backend_t metal,ggml_backend_t cpu,std::vector<weights> & all,const json & fixture,
              std::ofstream & evidence,int rows,const std::string & route,const std::string & layout,int route_index,bool perf) {
    const int copies=perf||layout=="chain"?8:1,samples=perf?60:1;
    auto ctx=ggml_init({ggml_tensor_overhead()*1024+ggml_graph_overhead_custom(1024,false),nullptr,true});
    require(ctx,"Graph context unavailable");auto graph=ggml_new_graph_custom(ctx,1024,false);
    std::vector<block_case> blocks;
    std::vector<std::pair<ggml_tensor *,std::vector<float>>> inputs;
    std::vector<std::pair<ggml_tensor *,std::vector<int>>> id_inputs;
    ggml_tensor * previous=nullptr;
    auto add_input=[&](ggml_tensor * tensor,std::vector<float> values) {
        ggml_set_input(tensor);ggml_set_output(tensor);inputs.push_back({tensor,std::move(values)});
    };
    auto make_ids=[&](const std::vector<int> & selected) {
        const int width=layout=="ids-contiguous"?10:512,offset=layout=="ids-offset"?7:0;
        auto storage=ggml_new_tensor_2d(ctx,GGML_TYPE_I32,width,rows);
        ggml_set_input(storage);ggml_set_output(storage);
        auto ids=ggml_view_2d(ctx,storage,10,rows,width*4,offset*4);
        std::vector<int> values(width*rows,-12345);
        for(int r=0;r<rows;++r) std::copy_n(selected.begin()+10*r,10,values.begin()+width*r+offset);
        id_inputs.push_back({storage,std::move(values)});return ids;
    };
    for(int copy=0;copy<copies;++copy) {
        auto selected=routing(fixture,rows,route,route_index+copy);
        ggml_tensor * x=previous;
        if(!x) {
            const int stride=2560+(layout=="input-strided"?8:0);
            auto input=ggml_new_tensor_3d(ctx,GGML_TYPE_F32,stride,1,rows);
            x=ggml_view_3d(ctx,input,2560,1,rows,stride*4,stride*4,0);
            std::vector<float> values(stride*rows,12345.0f);uint32_t state=0x815913;
            for(int r=0;r<rows;++r) for(int k=0;k<2560;++k) {
                state^=state<<13;state^=state>>17;state^=state<<5;
                float value=float(int32_t(state)%100000)/100000.0f;
                if(layout=="cancel")value=(k%2?-1.0f:1.0f)*1.00000011920928955f;
                if(layout=="wide")value=std::ldexp(value,k%13-6);
                values[r*stride+k]=value;
            }
            add_input(input,std::move(values));
        }
        auto ids=make_ids(selected);auto up_ids=selected;auto ids_up=ids;
        if(layout=="different-ids") {
            for(int & id:up_ids)id=(id+7)%512;
            ids_up=make_ids(up_ids);
        }
        auto up_x=layout=="different-input"?ggml_scale(ctx,x,1.125f):x;
        const int base=layout=="weights-strided"?6:(copy%2)*3;
        auto & gw=all[base];auto & uw=all[base+1];auto & dw=all[base+2];
        auto weight_view=[&](weights & w) {
            return layout=="weights-strided"?ggml_view_3d(ctx,w.tensor,w.k,w.m,512,w.tensor->nb[1],w.tensor->nb[2],0):w.tensor;
        };
        auto gate=ggml_mul_mat_id(ctx,weight_view(gw),x,ids);
        auto up=ggml_mul_mat_id(ctx,weight_view(uw),up_x,ids_up);
        ggml_tensor * gate_arg=gate;
        if(layout=="bias") {
            auto bias=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,640);add_input(bias,std::vector<float>(640,0.125f));
            gate_arg=ggml_add(ctx,gate,bias);
        }
        if(layout=="clamp")gate_arg=ggml_clamp(ctx,gate,-0.25f,0.25f);
        auto activated=layout=="reversed"?ggml_swiglu_split(ctx,up,gate_arg):
                       layout=="activation-unfused"?ggml_mul(ctx,ggml_silu(ctx,gate_arg),up):ggml_swiglu_split(ctx,gate_arg,up);
        auto down=ggml_mul_mat_id(ctx,weight_view(dw),activated,ids);
        if(layout=="retained"){ggml_set_output(gate);ggml_set_output(up);}
        ggml_set_output(activated);ggml_set_output(down);
        ggml_build_forward_expand(graph,down);
        ggml_tensor * extra=nullptr;
        if(layout=="external") {
            extra=ggml_scale(ctx,gate,0.5f);ggml_set_output(extra);ggml_build_forward_expand(graph,extra);
        }
        auto coefficients=ggml_new_tensor_3d(ctx,GGML_TYPE_F32,1,10,rows);
        add_input(coefficients,std::vector<float>(10*rows,0.1f));
        auto weighted=ggml_mul(ctx,down,coefficients);
        auto sum=ggml_view_2d(ctx,weighted,2560,rows,weighted->nb[2],0);
        for(int e=1;e<10;++e)sum=ggml_add(ctx,sum,ggml_view_2d(ctx,weighted,2560,rows,weighted->nb[2],e*weighted->nb[1]));
        previous=ggml_add(ctx,x,ggml_reshape_3d(ctx,sum,2560,1,rows));
        ggml_set_output(previous);ggml_build_forward_expand(graph,previous);
        blocks.push_back({&gw,&uw,&dw,x,gate,up,activated,down,previous,extra,std::move(selected),std::move(up_ids)});
    }
    // The pinned API requires a final CPU backend; every graph node is explicitly Metal.
    ggml_backend_t backends[]={metal,cpu};
    auto sched=ggml_backend_sched_new(backends,nullptr,2,1024,false,true);require(sched,"Scheduler unavailable");
    // INPUT leaves otherwise default to CPU. A manually placed Metal view must
    // share its base's backend: the scheduler skips view ops when making copies.
    for(const auto & entry:inputs)ggml_backend_sched_set_tensor_backend(sched,entry.first,metal);
    for(const auto & entry:id_inputs)ggml_backend_sched_set_tensor_backend(sched,entry.first,metal);
    for(int i=0;i<ggml_graph_n_nodes(graph);++i)ggml_backend_sched_set_tensor_backend(sched,ggml_graph_node(graph,i),metal);
    require(ggml_backend_sched_alloc_graph(sched,graph),"Scheduler allocation failed");
    auto require_metal_storage=[&](ggml_tensor * tensor) {
        auto storage=tensor->view_src?tensor->view_src:tensor;
        require(storage->buffer&&ggml_backend_buffer_get_type(storage->buffer)==ggml_backend_get_default_buffer_type(metal),
                "Tensor storage is not a Metal buffer");
    };
    for(int i=0;i<ggml_graph_n_nodes(graph);++i) {
        auto node=ggml_graph_node(graph,i);
        require(ggml_backend_sched_get_tensor_backend(sched,node)==metal,"Unexpected CPU graph placement");
        require_metal_storage(node);
        for(auto src:node->src)if(src)require_metal_storage(src);
    }
    for(const auto & entry:inputs)ggml_backend_tensor_set(entry.first,entry.second.data(),0,entry.second.size()*4);
    for(const auto & entry:id_inputs)ggml_backend_tensor_set(entry.first,entry.second.data(),0,entry.second.size()*4);
    std::vector<double> times;
    for(int i=-4;i<samples;++i) {
        auto start=std::chrono::steady_clock::now();
        require(ggml_backend_sched_graph_compute(sched,graph)==GGML_STATUS_SUCCESS,"Scheduled compute failed");
        ggml_backend_sched_synchronize(sched);
        if(i>=0)times.push_back(std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count()/copies);
    }
    check_stats stats;size_t elements=0;double max_tensor_nmse=0;
    auto check_write=[&](ggml_tensor * tensor,const std::vector<double> & expected) {
        auto actual=read_f32(tensor);require(actual.size()==expected.size(),"CPU reference length differs");
        check_stats local;
        for(size_t i=0;i<actual.size();++i){stats.add(actual[i],expected[i]);local.add(actual[i],expected[i]);}
        require(local.nmse()<1e-8&&local.max_scaled<1e-4,"Per-tensor CPU reference failed");
        max_tensor_nmse=std::max(max_tensor_nmse,local.nmse());
        if(!perf)evidence.write(reinterpret_cast<const char *>(actual.data()),actual.size()*4);
        elements+=actual.size();return actual;
    };
    for(auto & block:blocks) {
        std::vector<uint8_t> raw(ggml_nbytes(block.x));ggml_backend_tensor_get(block.x,raw.data(),0,raw.size());
        std::vector<float> x(2560*rows);
        for(int r=0;r<rows;++r)std::memcpy(x.data()+r*2560,raw.data()+r*block.x->nb[2],2560*4);
        auto ux=x;if(layout=="different-input")for(float & v:ux)v*=1.125f;
        auto g=reference_projection(*block.gate_w,x,block.ids,rows,1);
        auto u=reference_projection(*block.up_w,ux,block.up_ids,rows,1);
        if(layout=="retained"){check_write(block.gate,g);check_write(block.up,u);}
        if(block.extra){auto ref=g;for(double & v:ref)v*=0.5;check_write(block.extra,ref);}
        std::vector<double> act_ref(g.size());
        for(size_t i=0;i<g.size();++i) {
            double gate=g[i],up=u[i];
            if(layout=="bias")gate+=0.125;
            if(layout=="clamp")gate=std::max(-0.25,std::min(0.25,gate));
            if(layout=="reversed")std::swap(gate,up);
            act_ref[i]=(gate/(1.0+std::exp(-gate)))*up;
        }
        auto actual_act=check_write(block.activated,act_ref);
        auto d=reference_projection(*block.down_w,actual_act,block.ids,rows,10);
        auto actual_down=check_write(block.down,d);
        std::vector<double> bridge(2560*rows);
        for(int r=0;r<rows;++r)for(int k=0;k<2560;++k) {
            float sum=actual_down[(r*10)*2560+k]*0.1f;
            for(int e=1;e<10;++e)sum+=actual_down[(r*10+e)*2560+k]*0.1f;
            bridge[r*2560+k]=x[r*2560+k]+sum;
        }
        check_write(block.bridge,bridge);
    }
    require(stats.nmse()<1e-8&&stats.max_scaled<1e-4,"Strict CPU activation/down/bridge reference failed");
    for(const auto & entry:inputs) {
        auto after=read_f32(entry.first);
        require(after.size()==entry.second.size()&&std::memcmp(after.data(),entry.second.data(),after.size()*4)==0,"Input/padding changed");
    }
    for(const auto & entry:id_inputs) {
        std::vector<int> after(entry.second.size());ggml_backend_tensor_get(entry.first,after.data(),0,after.size()*4);
        require(after==entry.second,"IDs/padding changed");
    }
    std::vector<int> distinct;for(const auto & b:blocks)distinct.push_back(std::set<int>(b.ids.begin(),b.ids.end()).size());
    std::sort(times.begin(),times.end());
    json result={{"rows",rows},{"route",route},{"layout",layout},{"route_index",route_index},{"samples",samples},
        {"triplets_per_graph",copies},{"wall_us_per_triplet",times[times.size()/2]},{"wall_samples_us_per_triplet",times},
        {"cpu_nmse",max_tensor_nmse},{"max_absolute_error",stats.max_absolute},{"max_scaled_error",stats.max_scaled},
        {"input_ids_preserved",true},{"output_elements",elements},{"distinct_experts",distinct},{"eligible",eligible(rows,layout)},
        {"scheduler",true},{"cpu_compute_nodes",0},{"graph_buffer_bytes",ggml_backend_sched_get_buffer_size(sched,metal)}};
    ggml_backend_sched_free(sched);ggml_free(ctx);return result;
}

int main(int argc,char ** argv) {
    std::setvbuf(stdout,nullptr,_IOLBF,0);
    try {
        require(argc==4,"Usage: gate-probe check|perf fixtures.json outputs.bin");
        const std::string mode=argv[1];require(mode=="check"||mode=="perf","Unknown mode");
        json fixture;std::ifstream input(argv[2]);input>>fixture;
        std::ofstream evidence(argv[3],std::ios::binary);require(bool(evidence),"Output evidence unavailable");
        ggml_backend_load_all();auto metal=ggml_backend_init_by_name("MTL0",nullptr);auto cpu=ggml_backend_init_by_type(GGML_BACKEND_DEVICE_TYPE_CPU,nullptr);
        require(metal&&cpu,"Required backend unavailable");
        auto ctx=ggml_init({ggml_tensor_overhead()*64,nullptr,true});require(ctx,"Weight context failed");
        std::vector<weights> all;
        for(int copy=0;copy<2;++copy)for(int family=0;family<3;++family)
            all.push_back(make_weights(ctx,family==2?640:2560,family==2?2560:640,0x278291+copy*173+family*7919));
        for(int family=0;family<3;++family)
            all.push_back(make_weights(ctx,family==2?640:2560,family==2?2560:640,0x289371+family*7919,true));
        auto buffer=ggml_backend_alloc_ctx_tensors(ctx,metal);require(buffer,"Weight buffer failed");
        ggml_backend_buffer_set_usage(buffer,GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
        size_t bytes=0;for(auto & w:all){ggml_backend_tensor_set(w.tensor,w.packed.data(),0,w.packed.size());bytes+=w.packed.size();}
        int count=0;auto run=[&](int rows,const std::string & route,const std::string & layout,int index){
            printf("M5_GATE_CASE %s\n",run_case(metal,cpu,all,fixture,evidence,rows,route,layout,index,mode=="perf").dump().c_str());++count;
        };
        if(mode=="check") {
            for(int rows:{1,2,3,6})run(rows,"distinct","plain",0);
            for(int rows:{4,5}) {
                for(int index=0;index<8;++index)run(rows,"real","plain",index);
                for(std::string route:{"distinct","shared","duplicate","mixed"})run(rows,route,"plain",0);
                for(std::string layout:{"input-strided","weights-strided","ids-contiguous","ids-offset","retained","external","bias","clamp","different-ids","different-input","reversed","activation-unfused","cancel","wide"})
                    run(rows,"mixed",layout,0);
            }
            for(int rows:{4,5})run(rows,"real","chain",0);
        } else for(int rows:{4,5})for(std::string route:{"real","distinct","shared"})run(rows,route,"plain",0);
        for(auto & w:all){std::vector<uint8_t> after(w.packed.size());ggml_backend_tensor_get(w.tensor,after.data(),0,after.size());require(after==w.packed,"Weight bytes changed");}
        require(bool(evidence),"Evidence write failed");
        printf("M5_GATE_DONE %s\n",json({{"mode",mode},{"cases",count},{"weights_preserved",true},{"allocated_weight_bytes",bytes},{"scheduler",true},{"cpu_compute_nodes",0}}).dump().c_str());
        ggml_backend_buffer_free(buffer);ggml_free(ctx);ggml_backend_free(cpu);ggml_backend_free(metal);return 0;
    } catch(const std::exception & error){fprintf(stderr,"M5_GATE_ERROR %s\n",error.what());return 1;}
}
