#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-alloc.h"
#include <nlohmann/json.hpp>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

using json = nlohmann::json;
void require(bool value, const char * message) { if (!value) throw std::runtime_error(message); }
uint32_t bits(float value) { uint32_t result; std::memcpy(&result, &value, 4); return result; }

struct fusion_api {
    void * context = nullptr;
    void (*reset)(void *) = nullptr;
    int (*get)(void *, const char **, uint64_t *, int) = nullptr;
    explicit fusion_api(ggml_backend_dev_t device, bool enabled) {
        if (!enabled) return;
        auto reg = ggml_backend_dev_backend_reg(device);
        auto resolve = [&](const char * name) {
            auto result = ggml_backend_reg_get_proc_address(reg, name);
            require(result, "Fusion diagnostics unavailable"); return result;
        };
        context = ((void * (*)(ggml_backend_dev_t))resolve("ggml_backend_fusion_get"))(device);
        ((void (*)(void *))resolve("ggml_backend_fusion_stats_init"))(context);
        reset = (void (*)(void *))resolve("ggml_backend_fusion_stats_reset");
        get = (int (*)(void *, const char **, uint64_t *, int))resolve("ggml_backend_fusion_stats_get");
    }
    json counts() const {
        json result = json::object();
        if (!context) return result;
        const char * labels[64]; uint64_t counts[64];
        const int n = get(context, labels, counts, 64);
        require(n >= 0 && n <= 64, "Fusion diagnostics overflow");
        for (int i=0; i<n; ++i) if (counts[i]) result[labels[i]] = counts[i];
        return result;
    }
};

json run_case(ggml_backend_t backend, fusion_api & api, std::ofstream & binary,
              int width, int rows, int experts, const std::string & layout, int samples) {
    auto ctx = ggml_init({ggml_tensor_overhead()*128 + ggml_graph_overhead_custom(128, false), nullptr, true});
    require(ctx, "Context allocation failed");
    const int stride = width + (layout == "strided" ? 4 : 0);
    auto input = ggml_new_tensor_3d(ctx, GGML_TYPE_F32, stride, experts, rows);
    auto weights = ggml_new_tensor_3d(ctx, GGML_TYPE_F32, 1, experts, rows);
    auto x = stride == width ? input : ggml_view_3d(ctx, input, width, experts, rows, stride*4, stride*experts*4, 0);
    auto weighted = ggml_mul(ctx, x, weights);
    auto graph = ggml_new_graph_custom(ctx, 128, false);
    ggml_build_forward_expand(graph, weighted);
    std::vector<ggml_tensor *> views;
    for (int e=0; e<experts; ++e) {
        views.push_back(ggml_view_2d(ctx, weighted, width, rows, weighted->nb[2], e*weighted->nb[1]));
        ggml_build_forward_expand(graph, views.back());
    }
    auto out = views[0];
    for (int e=1; e<experts; ++e) {
        out = ggml_add(ctx, out, views[layout == "reversed" ? experts-e : e]);
        ggml_build_forward_expand(graph, out);
    }
    if (layout == "exposed") {
        ggml_set_output(weighted);
        ggml_build_forward_expand(graph, ggml_sqr(ctx, weighted));
    }
    auto buffer = ggml_backend_alloc_ctx_tensors(ctx, backend); require(buffer, "Backend allocation failed");
    if (layout == "alias") { out->data=input->data; out->buffer=input->buffer; }
    std::vector<float> values(stride*experts*rows, 12345.0f), w(experts*rows);
    uint32_t state = 0x5719ab31;
    for (int t=0; t<rows; ++t) for (int e=0; e<experts; ++e) {
        w[t*experts+e] = float(e+1)/float(experts*(experts+1)/2);
        for (int c=0; c<width; ++c) {
            state ^= state<<13; state ^= state>>17; state ^= state<<5;
            float value = float(int32_t(state)%100000)/3107.0f;
            if (layout == "cancel") value = (e%2 ? -1.0f : 1.0f)*std::ldexp(1.00000011920928955f, e%8);
            if (layout == "special") {
                const uint32_t patterns[] = {0, 0x80000000, 0x7f800000, 0xff800000, 0x7fc01234, 1, 0x00800000};
                const uint32_t pattern = patterns[c%7]; std::memcpy(&value, &pattern, 4);
            }
            values[(t*experts+e)*stride+c] = value;
        }
    }
    ggml_backend_tensor_set(input, values.data(), 0, values.size()*4);
    ggml_backend_tensor_set(weights, w.data(), 0, w.size()*4);
    if (api.context) api.reset(api.context);
    std::vector<double> times;
    for (int i=-4; i<samples; ++i) {
        if (layout == "alias") ggml_backend_tensor_set(input, values.data(), 0, values.size()*4);
        const auto start = std::chrono::steady_clock::now();
        require(ggml_backend_graph_compute(backend, graph) == GGML_STATUS_SUCCESS, "GPU computation failed");
        ggml_backend_synchronize(backend);
        if (i>=0) times.push_back(std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count());
    }
    std::vector<float> actual(width*rows), after(values.size());
    ggml_backend_tensor_get(out, actual.data(), 0, actual.size()*4);
    ggml_backend_tensor_get(input, after.data(), 0, after.size()*4);
    auto preserved=values;
    if (layout == "alias") std::copy(actual.begin(),actual.end(),preserved.begin());
    require(std::memcmp(preserved.data(), after.data(), values.size()*4)==0, "Input or input padding changed outside the output alias");
    size_t differences = 0, classified = 0; double max_error = 0;
    for (int t=0; t<rows; ++t) for (int c=0; c<width; ++c) {
        volatile float sum = values[t*experts*stride+c]*w[t*experts];
        for (int e=1; e<experts; ++e) {
            const int selected = layout == "reversed" ? experts-e : e;
            volatile float product = values[(t*experts+selected)*stride+c]*w[t*experts+selected];
            sum = sum+product;
        }
        const float expected = sum, got = actual[t*width+c];
        if (std::isnan(expected) && std::isnan(got)) { ++classified; continue; }
        if (bits(expected)!=bits(got)) {
            ++differences;
            if (std::isfinite(expected) && std::isfinite(got)) max_error=std::max(max_error, double(std::abs(expected-got)));
        }
    }
    binary.write((const char *)actual.data(), actual.size()*4);
    require(bool(binary), "Output evidence write failed");
    std::sort(times.begin(), times.end());
    json result = {{"width",width},{"rows",rows},{"experts",experts},{"layout",layout},
        {"elements",actual.size()},{"samples",samples},{"wall_us",times[times.size()/2]},
        {"cpu_bit_differences",differences},{"nan_class_matches",classified},{"cpu_max_abs_error",max_error},
        {"fusions",api.counts()},{"input_preserved",true}};
    ggml_backend_buffer_free(buffer); ggml_free(ctx);
    return result;
}

int main(int argc, char ** argv) {
    try {
        require(argc==3, "Usage: reduce-probe check|perf output.bin");
        const std::string mode=argv[1]; require(mode=="check"||mode=="perf", "Unknown mode");
        std::ofstream binary(argv[2], std::ios::binary); require(bool(binary), "Output evidence file unavailable");
        ggml_backend_load_all();
        auto device=ggml_backend_dev_by_name("MTL0"); require(device, "Metal unavailable");
        fusion_api api(device, mode=="check");
        auto backend=ggml_backend_dev_init(device, nullptr); require(backend, "Metal backend unavailable");
        int cases=0;
        for (int rows : {1,3,4,5}) {
            if (mode=="check") {
                for (int width : {7,2560,2563}) for (const std::string layout : {"plain","strided","exposed","reversed","cancel","special","alias"}) {
                    auto r=run_case(backend,api,binary,width,rows,10,layout,1);
                    std::fprintf(stderr,"M5_REDUCE_CASE %s\n",r.dump().c_str()); ++cases;
                }
                for (int experts : {2,3,4,5,6,7,8,9,11}) {
                    auto r=run_case(backend,api,binary,67,rows,experts,"plain",1);
                    std::fprintf(stderr,"M5_REDUCE_CASE %s\n",r.dump().c_str()); ++cases;
                }
            } else {
                auto r=run_case(backend,api,binary,2560,rows,10,"plain",100);
                std::fprintf(stderr,"M5_REDUCE_CASE %s\n",r.dump().c_str()); ++cases;
            }
        }
        ggml_backend_free(backend);
        std::fprintf(stderr,"M5_REDUCE_DONE %s\n",json({{"mode",mode},{"cases",cases}}).dump().c_str());
        return 0;
    } catch (const std::exception & error) { std::fprintf(stderr,"M5_REDUCE_ERROR %s\n",error.what()); return 1; }
}
