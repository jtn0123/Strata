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
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

using json=nlohmann::json;
void require(bool value,const char * message) {if(!value) throw std::runtime_error(message);}

json run_case(ggml_backend_t backend,std::ofstream & evidence,int k,int m,int rows,const std::string & layout,bool perf) {
    const int copies=perf?20:1,samples=perf?60:1,stride=k+(layout=="strided"?8:0);
    auto ctx=ggml_init({ggml_tensor_overhead()*256+ggml_graph_overhead_custom(256,false),nullptr,true});
    require(ctx,"Context failed");
    std::vector<ggml_tensor *> weight_tensors;
    for(int i=0;i<copies;++i) weight_tensors.push_back(ggml_new_tensor_2d(ctx,GGML_TYPE_BF16,k,m));
    auto input=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,stride,rows);
    auto x=stride==k?input:ggml_view_2d(ctx,input,k,rows,stride*4,0);
    auto residual=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,m,rows);
    auto graph=ggml_new_graph_custom(ctx,256,false);
    std::vector<ggml_tensor *> outputs;
    for(int i=0;i<copies;++i) {
        auto matrix=ggml_mul_mat(ctx,weight_tensors[i],x);
        auto out=layout=="residual"||layout=="exposed"?ggml_add(ctx,matrix,residual):matrix;
        if(layout=="exposed") ggml_set_output(matrix);
        ggml_set_output(out);ggml_build_forward_expand(graph,out);outputs.push_back(out);
        if(layout=="exposed") ggml_build_forward_expand(graph,ggml_sqr(ctx,matrix));
    }
    auto buffer=ggml_backend_alloc_ctx_tensors(ctx,backend);require(buffer,"Buffer failed");
    std::vector<float> weights(k*m),values(stride*rows,12345.0f),res(m*rows);
    std::vector<ggml_bf16_t> packed(k*m);
    uint32_t state=0x189537f;
    auto random=[&]() {state^=state<<13;state^=state>>17;state^=state<<5;return float(int32_t(state)%100000)/100000.0f;};
    const float scale=1.0f/std::sqrt(float(k));
    for(int i=0;i<k*m;++i) {packed[i]=ggml_fp32_to_bf16(random()*scale);weights[i]=ggml_bf16_to_fp32(packed[i]);}
    for(int r=0;r<rows;++r) for(int j=0;j<k;++j) {
        float value=random();
        if(layout=="cancel") value=(j%2?-1.0f:1.0f)*1.00000011920928955f;
        if(layout=="wide") value=std::ldexp(value,j%17-12);
        values[r*stride+j]=value;
    }
    for(auto & value:res) value=random();
    for(auto w:weight_tensors) ggml_backend_tensor_set(w,packed.data(),0,packed.size()*2);
    ggml_backend_tensor_set(input,values.data(),0,values.size()*4);
    ggml_backend_tensor_set(residual,res.data(),0,res.size()*4);
    std::vector<double> times;
    for(int i=-4;i<samples;++i) {
        const auto start=std::chrono::steady_clock::now();
        require(ggml_backend_graph_compute(backend,graph)==GGML_STATUS_SUCCESS,"Graph failed");
        ggml_backend_synchronize(backend);
        if(i>=0) times.push_back(std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count()/copies);
    }
    std::vector<float> actual(m*rows),reference(m*rows),after(values.size());
    ggml_backend_tensor_get(outputs.back(),actual.data(),0,actual.size()*4);
    double error=0,denom=0,max_error=0;
    for(int r=0;r<rows;++r) for(int col=0;col<m;++col) {
        double sum=0;
        for(int j=0;j<k;++j) sum+=double(weights[col*k+j])*values[r*stride+j];
        if(layout=="residual"||layout=="exposed") sum+=res[r*m+col];
        const int i=r*m+col;reference[i]=float(sum);
        const double e=actual[i]-sum;error+=e*e;denom+=sum*sum;max_error=std::max(max_error,std::abs(e));
    }
    const double nmse=error/std::max(denom,1e-30);
    require(std::isfinite(nmse)&&nmse<1e-8&&max_error<0.0001,"Strict CPU-reference accuracy failed");
    ggml_backend_tensor_get(input,after.data(),0,after.size()*4);
    require(after==values,"Input or stride padding changed");
    std::vector<ggml_bf16_t> after_weights(packed.size());
    for(auto w:weight_tensors) {
        ggml_backend_tensor_get(w,after_weights.data(),0,packed.size()*2);
        require(std::memcmp(after_weights.data(),packed.data(),packed.size()*2)==0,"Weights changed");
    }
    if(!perf) evidence.write(reinterpret_cast<const char *>(actual.data()),actual.size()*4);
    std::sort(times.begin(),times.end());
    const json result={{"k",k},{"m",m},{"rows",rows},{"layout",layout},{"samples",samples},
        {"copies_per_graph",copies},{"distinct_weight_bytes",packed.size()*2*copies},{"wall_us_per_op",times[times.size()/2]},
        {"cpu_nmse",nmse},{"max_absolute_error",max_error},{"input_preserved",true},{"elements",actual.size()}};
    ggml_backend_buffer_free(buffer);ggml_free(ctx);return result;
}

int main(int argc,char ** argv) {
    // Keep JSON markers intact when backend diagnostics share the log file.
    std::setvbuf(stdout,nullptr,_IOLBF,0);
    try {
        require(argc==3,"Usage: hc-probe check|perf outputs.bin");
        const std::string mode=argv[1];require(mode=="check"||mode=="perf","Unknown mode");
        std::ofstream evidence(argv[2],std::ios::binary);
        ggml_backend_load_all();auto backend=ggml_backend_init_by_name("MTL0",nullptr);require(backend,"Metal unavailable");
        int count=0;
        for(auto shape:{std::pair<int,int>{10240,320},{320,10240}}) {
            for(int rows:{1,2,3,4,5,8}) {
                for(std::string layout:mode=="check"?std::vector<std::string>{"plain","residual","exposed","strided","cancel","wide"}:std::vector<std::string>{"plain","residual"}) {
                    const auto result=run_case(backend,evidence,shape.first,shape.second,rows,layout,mode=="perf");
                    printf("M5_HC_CASE %s\n",result.dump().c_str());++count;
                }
            }
        }
        printf("M5_HC_DONE %s\n",json({{"mode",mode},{"cases",count}}).dump().c_str());
        ggml_backend_free(backend);return 0;
    } catch(const std::exception & error) {fprintf(stderr,"M5_HC_ERROR %s\n",error.what());return 1;}
}
