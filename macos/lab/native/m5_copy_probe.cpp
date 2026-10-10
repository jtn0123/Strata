#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-alloc.h"
#include <nlohmann/json.hpp>
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

using json = nlohmann::json;
using shape = std::array<int64_t, 4>;
using strides = std::array<size_t, 4>;

void require(bool ok, const char * message) { if (!ok) throw std::runtime_error(message); }
size_t span(shape ne, strides nb) {
    size_t n = 4;
    for (int d = 0; d < 4; ++d) n += (ne[d]-1)*nb[d];
    return n;
}
size_t offset(int64_t i, shape ne, strides nb) {
    size_t n = 0;
    for (int d = 0; d < 4; ++d) { n += (i % ne[d])*nb[d]; i /= ne[d]; }
    return n;
}

void run_case(ggml_backend_t backend, int width, int rows, const std::string & layout, int samples) {
    shape sn = {width, 1, rows, 1}, dn = sn;
    if (layout == "four-dimensional") sn = dn = {width, 2, rows, 2};
    strides sb = {4, size_t(width)*4, size_t(width)*4, size_t(width)*4*rows};
    strides db = sb;
    if (layout == "four-dimensional") {
        sb = {4, size_t(width+4)*4, size_t(width+4)*8, size_t(width+4)*8*rows};
        db = {4, size_t(width+8)*4, size_t(width+8)*8, size_t(width+8)*8*rows};
    }
    if (layout == "strided") {
        sb[2] += 16; db[2] = size_t(width)*4*6;
        sb[3] = sb[2]*rows; db[3] = db[2]*rows;
    }
    if (layout == "odd-stride") { sb[2] += 4; sb[3] = sb[2]*rows; }
    if (layout == "aligned-tail") {
        sb[2] = size_t((width+3)/4)*16; db[2] = sb[2]+16;
        sb[3] = sb[2]*rows; db[3] = db[2]*rows;
    }
    if (layout == "reshape") { dn = {int64_t(width)*rows,1,1,1}; db = {4,size_t(width)*rows*4,size_t(width)*rows*4,size_t(width)*rows*4}; }
    if (layout == "transposed") {
        sn = {width,rows,1,1}; dn = sn;
        sb = {size_t(rows)*4,4,size_t(width)*rows*4,size_t(width)*rows*4};
        db = {4,size_t(width)*4,size_t(width)*rows*4,size_t(width)*rows*4};
    }
    if (layout == "conv-tail" || layout == "conv-cont-tail") {
        sn = {3,10240,rows,1}; dn = {30720,rows,1,1};
        sb = {4,44,44*10240,44*10240*size_t(rows)};
        db = {4,30720*4,30720*4*size_t(rows),30720*4*size_t(rows)};
    }
    const size_t src_start = layout == "unaligned" ? 4 : 16;
    const size_t dst_start = layout == "unaligned" ? 12 : 32;
    const size_t src_bytes = src_start + span(sn,sb) + 64;
    const size_t dst_bytes = dst_start + span(dn,db) + 64;
    std::vector<uint32_t> input(src_bytes/4), expected(dst_bytes/4,0xa5a5a5a5), actual(expected.size());
    uint32_t state = 0x918372ab;
    for (auto & x : input) { state ^= state << 13; state ^= state >> 17; state ^= state << 5; x = state; }
    const uint32_t specials[] = {0,0x80000000,0x7f800000,0xff800000,0x7fc01234,0x7f801234,1,0x80000001};
    for (int i=0;i<8;++i) input[src_start/4+i] = specials[i];
    const int64_t count = sn[0]*sn[1]*sn[2]*sn[3];
    for (int64_t i=0;i<count;++i) expected[(dst_start+offset(i,dn,db))/4] = input[(src_start+offset(i,sn,sb))/4];
    ggml_init_params params = {ggml_tensor_overhead()*32 + ggml_graph_overhead_custom(32,false),nullptr,true};
    auto ctx = ggml_init(params); require(ctx,"Context allocation failed");
    auto src_base = ggml_new_tensor_1d(ctx,GGML_TYPE_F32,input.size());
    auto dst_base = ggml_new_tensor_1d(ctx,GGML_TYPE_F32,actual.size());
    ggml_tensor * src;
    if (layout == "transposed") {
        src = ggml_transpose(ctx,ggml_view_2d(ctx,src_base,rows,width,size_t(rows)*4,src_start));
    } else {
        src = ggml_view_4d(ctx,src_base,sn[0],sn[1],sn[2],sn[3],sb[1],sb[2],sb[3],src_start);
    }
    auto dst = ggml_view_4d(ctx,dst_base,dn[0],dn[1],dn[2],dn[3],db[1],db[2],db[3],dst_start);
    auto out = ggml_cpy(ctx,layout == "conv-cont-tail" ? ggml_cont(ctx,src) : src,dst);
    auto graph = ggml_new_graph_custom(ctx,32,false); ggml_build_forward_expand(graph,out);
    auto buffer = ggml_backend_alloc_ctx_tensors(ctx,backend); require(buffer,"Backend allocation failed");
    ggml_backend_tensor_set(src_base,input.data(),0,src_bytes);
    ggml_backend_tensor_set(dst_base,expected.data(),0,dst_bytes);
    std::fill(actual.begin(),actual.end(),0xa5a5a5a5);
    ggml_backend_tensor_set(dst_base,actual.data(),0,dst_bytes);
    const json base = {{"width",width},{"rows",rows},{"layout",layout},{"copy_bytes",count*4},
                       {"src_ne",sn},{"dst_ne",dn},{"src_nb",sb},{"dst_nb",db}};
    for (int sample=-3;sample<samples;++sample) {
        auto marker = base; marker["phase"] = sample<0 ? "warmup" : "measure"; marker["sample"] = sample;
        std::fprintf(stderr,"M5_COPY_CALL %s\n",marker.dump().c_str());
        const auto start = std::chrono::steady_clock::now();
        require(ggml_backend_graph_compute(backend,graph)==GGML_STATUS_SUCCESS,"Graph failed");
        ggml_backend_synchronize(backend);
        marker["wall_us"] = std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count();
        std::fprintf(stderr,"M5_COPY_RETURN %s\n",marker.dump().c_str());
    }
    ggml_backend_tensor_get(dst_base,actual.data(),0,dst_bytes);
    require(actual==expected,"Copied values or untouched destination padding differ bit for bit");
    std::vector<uint32_t> source_after(input.size());
    ggml_backend_tensor_get(src_base,source_after.data(),0,src_bytes);
    require(source_after==input,"Source was changed");
    std::fprintf(stderr,"M5_COPY_PASS %s\n",base.dump().c_str());
    ggml_backend_buffer_free(buffer); ggml_free(ctx);
}

int main(int argc,char ** argv) {
    try {
        require(argc==2,"Usage: copy-probe test|perf");
        const std::string mode(argv[1]); require(mode=="test"||mode=="perf","Unknown mode");
        ggml_backend_load_all();
        auto backend = ggml_backend_init_by_name("MTL0",nullptr); require(backend,"Metal unavailable");
        int cases=0;
        if (mode=="test") {
            for (int width : {7,4095,4096,4097,65536}) {
                for (const std::string layout : {"contiguous","strided","odd-stride","unaligned","reshape","transposed","four-dimensional"}) {
                    run_case(backend,width,4,layout,1); ++cases;
                }
            }
            for (int rows : {1,4,5}) {
                for (const std::string layout : {"contiguous","strided"}) { run_case(backend,786432,rows,layout,1); ++cases; }
            }
            for (int rows : {1,2,4}) {
                for (const std::string layout : {"conv-tail","conv-cont-tail"}) { run_case(backend,3,rows,layout,1); ++cases; }
            }
            for (int width : {4097,4113,4132}) {
                for (int rows : {1,4,5}) { run_case(backend,width,rows,"aligned-tail",1); ++cases; }
            }
        } else {
            for (int rows : {1,4,5}) {
                for (const std::string layout : {"contiguous","strided"}) { run_case(backend,786432,rows,layout,40); ++cases; }
            }
        }
        ggml_backend_free(backend);
        std::fprintf(stderr,"M5_COPY_DONE %s\n",json({{"mode",mode},{"passed",cases}}).dump().c_str());
        return 0;
    } catch (const std::exception & error) { std::fprintf(stderr,"M5_COPY_ERROR %s\n",error.what()); return 1; }
}
