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

struct projection { weights * w; ggml_tensor * input; ggml_tensor * output; };

json run_case(ggml_backend_t backend, std::vector<weights> & all, const json & fixture,
              std::ofstream & evidence, int rows, const std::string & route,
              const std::string & layout, int route_index, bool perf) {
    const int copies=perf||layout=="chain"?8:1,samples=perf?60:1;
    auto ctx=ggml_init({ggml_tensor_overhead()*512+ggml_graph_overhead_custom(512,false),nullptr,true});
    require(ctx,"Graph context unavailable");
    auto graph=ggml_new_graph_custom(ctx,512,false);
    std::vector<projection> ops;
    std::vector<std::pair<ggml_tensor *,std::vector<float>>> inputs;
    std::vector<std::pair<ggml_tensor *,std::vector<int>>> id_inputs;
    std::vector<std::vector<int>> routes;
    ggml_tensor * previous=nullptr;
    size_t elements=0;
    for(int copy=0;copy<copies;++copy) {
        auto selected=routing(fixture,rows,route,route_index+copy);routes.push_back(selected);
        const int stride=2560+(layout=="input-strided"?8:0);
        auto input=ggml_new_tensor_3d(ctx,GGML_TYPE_F32,stride,1,rows);
        auto x=ggml_view_3d(ctx,input,2560,1,rows,stride*4,stride*4,0);
        if(previous) x=previous;
        std::vector<float> values(stride*rows,12345.0f);
        uint32_t state=0x815913+copy*7919;
        for(int r=0;r<rows;++r) for(int k=0;k<2560;++k) {
            state^=state<<13;state^=state>>17;state^=state<<5;
            float value=float(int32_t(state)%100000)/100000.0f;
            if(layout=="cancel") value=(k%2?-1.0f:1.0f)*1.00000011920928955f;
            if(layout=="wide") value=std::ldexp(value,k%13-6);
            values[r*stride+k]=value;
        }
        inputs.push_back({input,std::move(values)});
        const int id_width=layout=="ids-contiguous"?10:512;
        auto ids_storage=ggml_new_tensor_2d(ctx,GGML_TYPE_I32,id_width,rows);
        const int offset=layout=="ids-offset"?7:0;
        auto ids=ggml_view_2d(ctx,ids_storage,10,rows,id_width*4,offset*4);
        std::vector<int> full_ids(id_width*rows,-12345);
        for(int r=0;r<rows;++r) std::copy_n(selected.begin()+r*10,10,full_ids.begin()+r*id_width+offset);
        id_inputs.push_back({ids_storage,std::move(full_ids)});
        auto weight_view=[&](weights & w) {
            return layout=="weights-strided" ? ggml_view_3d(ctx,w.tensor,w.k,w.m,512,w.tensor->nb[1],w.tensor->nb[2],0) : w.tensor;
        };
        const int base=layout=="weights-strided"?6:(copy%2)*3;
        auto & gate_w=all[base];auto & up_w=all[base+1];auto & down_w=all[base+2];
        auto gate=ggml_mul_mat_id(ctx,weight_view(gate_w),x,ids);
        auto up=ggml_mul_mat_id(ctx,weight_view(up_w),x,ids);
        auto activated=ggml_swiglu_split(ctx,gate,up);
        auto down=ggml_mul_mat_id(ctx,weight_view(down_w),activated,ids);
        ops.push_back({&gate_w,x,gate});ops.push_back({&up_w,x,up});ops.push_back({&down_w,activated,down});
        // MUL_MAT_ID has no gate/up fusion in this pin. Diagnostic outputs are
        // retained only in check mode; perf is the ordinary complete graph.
        if(!perf) {ggml_set_output(gate);ggml_set_output(up);ggml_set_output(activated);}
        ggml_set_output(down);ggml_build_forward_expand(graph,down);
        if(copies>1) {
            auto coefficients=ggml_new_tensor_3d(ctx,GGML_TYPE_F32,1,10,rows);
            inputs.push_back({coefficients,std::vector<float>(10*rows,0.1f)});
            auto weighted=ggml_mul(ctx,down,coefficients);
            auto sum=ggml_view_2d(ctx,weighted,2560,rows,weighted->nb[2],0);
            for(int e=1;e<10;++e) sum=ggml_add(ctx,sum,ggml_view_2d(ctx,weighted,2560,rows,weighted->nb[2],e*weighted->nb[1]));
            // Data dependency models sequential expert blocks; residual keeps
            // later activations well-scaled. Bridge cost is included in timings.
            previous=ggml_add(ctx,x,ggml_reshape_3d(ctx,sum,2560,1,rows));
            ggml_set_output(previous);ggml_build_forward_expand(graph,previous);
        }
        elements+=size_t(640+640+2560)*10*rows;
    }
    auto buffer=ggml_backend_alloc_ctx_tensors(ctx,backend);require(buffer,"Graph buffer unavailable");
    for(const auto & entry:inputs) ggml_backend_tensor_set(entry.first,entry.second.data(),0,entry.second.size()*4);
    for(const auto & entry:id_inputs) ggml_backend_tensor_set(entry.first,entry.second.data(),0,entry.second.size()*4);
    std::vector<double> times;
    for(int i=-4;i<samples;++i) {
        auto start=std::chrono::steady_clock::now();
        require(ggml_backend_graph_compute(backend,graph)==GGML_STATUS_SUCCESS,"Graph compute failed");
        ggml_backend_synchronize(backend);
        if(i>=0) times.push_back(std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count()/copies);
    }
    double error=0,denom=0,max_error=0;
    std::vector<float> dequant(2560);
    for(size_t index=0;index<ops.size();++index) {
        auto & op=ops[index];auto & w=*op.w;
        std::vector<uint8_t> raw(ggml_nbytes(op.input));
        ggml_backend_tensor_get(op.input,raw.data(),0,raw.size());
        std::vector<float> actual(w.m*10*rows);
        ggml_backend_tensor_get(op.output,actual.data(),0,actual.size()*4);
        const auto & ids=routes[index/3];
        for(int r=0;r<rows;++r) for(int e=0;e<10;++e) for(int col=0;col<w.m;++col) {
            const auto * packed=w.packed.data()+ids[r*10+e]*w.tensor->nb[2]+col*w.tensor->nb[1];
            ggml_get_type_traits(GGML_TYPE_Q2_0)->to_float(packed,dequant.data(),w.k);
            const float * x=reinterpret_cast<const float *>(raw.data()+r*op.input->nb[2]+(e%op.input->ne[1])*op.input->nb[1]);
            double sum=0;for(int k=0;k<w.k;++k) sum+=double(dequant[k])*x[k];
            double difference=actual[(r*10+e)*w.m+col]-sum;
            require(std::isfinite(difference),"Non-finite reference or output");
            error+=difference*difference;denom+=sum*sum;max_error=std::max(max_error,std::abs(difference));
        }
        if(!perf) evidence.write(reinterpret_cast<const char *>(actual.data()),actual.size()*4);
    }
    const double nmse=error/std::max(denom,1e-30);
    require(nmse<1e-8&&max_error<0.0001,"Strict CPU projection reference failed");
    for(const auto & entry:inputs) {
        std::vector<float> after(entry.second.size());ggml_backend_tensor_get(entry.first,after.data(),0,after.size()*4);
        require(std::memcmp(after.data(),entry.second.data(),after.size()*4)==0,"Input or padding changed");
    }
    for(const auto & entry:id_inputs) {
        std::vector<int> after(entry.second.size());ggml_backend_tensor_get(entry.first,after.data(),0,after.size()*4);
        require(after==entry.second,"Expert IDs or padding changed");
    }
    std::vector<int> distinct;
    for(const auto & ids:routes) distinct.push_back(std::set<int>(ids.begin(),ids.end()).size());
    std::sort(times.begin(),times.end());
    json result={{"rows",rows},{"route",route},{"route_index",route_index},{"layout",layout},
        {"samples",samples},{"triplets_per_graph",copies},{"wall_us_per_triplet",times[times.size()/2]},
        {"cpu_nmse",nmse},{"max_absolute_error",max_error},{"input_ids_preserved",true},
        {"elements",elements},{"distinct_experts",distinct}};
    ggml_backend_buffer_free(buffer);ggml_free(ctx);return result;
}

int main(int argc,char ** argv) {
    std::setvbuf(stdout,nullptr,_IOLBF,0);
    try {
        require(argc==4,"Usage: group-probe check|perf fixtures.json outputs.bin");
        const std::string mode=argv[1];require(mode=="check"||mode=="perf","Unknown mode");
        json fixture;std::ifstream input(argv[2]);input>>fixture;
        std::ofstream evidence(argv[3],std::ios::binary);require(bool(evidence),"Output evidence unavailable");
        ggml_backend_load_all();auto backend=ggml_backend_init_by_name("MTL0",nullptr);require(backend,"Metal unavailable");
        auto ctx=ggml_init({ggml_tensor_overhead()*64,nullptr,true});require(ctx,"Weight context failed");
        std::vector<weights> all;
        for(int copy=0;copy<2;++copy) for(int family=0;family<3;++family)
            all.push_back(make_weights(ctx,family==2?640:2560,family==2?2560:640,0x278291+copy*173+family*7919));
        for(int family=0;family<3;++family)
            all.push_back(make_weights(ctx,family==2?640:2560,family==2?2560:640,0x289371+family*7919,true));
        auto buffer=ggml_backend_alloc_ctx_tensors(ctx,backend);require(buffer,"Weight buffer failed");
        size_t bytes=0;for(auto & w:all) {ggml_backend_tensor_set(w.tensor,w.packed.data(),0,w.packed.size());bytes+=w.packed.size();}
        int count=0;
        auto run=[&](int rows,const std::string & route,const std::string & layout,int index) {
            printf("M5_GROUP_CASE %s\n",run_case(backend,all,fixture,evidence,rows,route,layout,index,mode=="perf").dump().c_str());++count;
        };
        if(mode=="check") {
            for(int rows:{1,2,3,6}) run(rows,"distinct","plain",0);
            for(int rows:{4,5}) {
                for(int index=0;index<8;++index) run(rows,"real","plain",index);
                for(std::string route:{"distinct","shared","duplicate","mixed"}) run(rows,route,"plain",0);
                for(std::string layout:{"input-strided","ids-contiguous","ids-offset","weights-strided","cancel","wide"}) run(rows,"mixed",layout,0);
            }
            for(int rows:{4,5}) run(rows,"real","chain",0);
        } else for(int rows:{4,5}) for(std::string route:{"real","distinct","shared"}) run(rows,route,"plain",0);
        // Verify every weight byte outside timed regions.
        for(auto & w:all) {
            std::vector<uint8_t> after(w.packed.size());ggml_backend_tensor_get(w.tensor,after.data(),0,after.size());
            require(after==w.packed,"Weight bytes changed");
        }
        printf("M5_GROUP_DONE %s\n",json({{"mode",mode},{"cases",count},{"weights_preserved",true},{"allocated_weight_bytes",bytes}}).dump().c_str());
        ggml_backend_buffer_free(buffer);ggml_free(ctx);ggml_backend_free(backend);return 0;
    } catch(const std::exception & error) {fprintf(stderr,"M5_GROUP_ERROR %s\n",error.what());return 1;}
}
