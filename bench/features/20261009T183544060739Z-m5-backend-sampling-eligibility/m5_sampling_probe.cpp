#include "llama.h"
#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-alloc.h"
#include "ggml-metal.h"
#include <nlohmann/json.hpp>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <vector>

using json = nlohmann::json;
static void require(bool ok, const char * message) {
    if (!ok) throw std::runtime_error(message);
}

static json run_case(ggml_backend_t metal, float p, bool sorted, bool boundary) {
    const float threshold = std::log(p);
    std::vector<float> logits = boundary ? std::vector<float>{0.0f, threshold + 0.01f,
        std::nextafter(threshold, INFINITY), threshold, std::nextafter(threshold, -INFINITY), threshold - 0.01f, -20.0f}
        : std::vector<float>{0.0f, threshold + 0.04f, threshold + 0.02f, threshold + 0.01f,
                            threshold - 0.01f, threshold - 0.02f, -20.0f};
    if (sorted) std::sort(logits.begin(), logits.end(), std::greater<float>());
    std::vector<llama_token_data> tokens;
    for (size_t i = 0; i < logits.size(); ++i) tokens.push_back({llama_token(i), logits[i], 0.0f});
    llama_token_data_array array = {tokens.data(), tokens.size(), -1, sorted};
    auto host = llama_sampler_init_min_p(p, 0);
    llama_sampler_apply(host, &array);
    std::vector<int> cpu_ids;
    for (size_t i = 0; i < array.size; ++i) cpu_ids.push_back(array.data[i].id);
    llama_sampler_free(host);

    auto sampler = llama_sampler_init_min_p(p, 0);
    require(sampler->iface->backend_init && sampler->iface->backend_apply, "Backend sampler unavailable");
    require(sampler->iface->backend_init(sampler, ggml_backend_get_default_buffer_type(metal), 1), "Metal sampler unsupported");
    auto ctx = ggml_init({ggml_tensor_overhead()*256 + ggml_graph_overhead_custom(256, false), nullptr, true});
    require(ctx, "Context allocation failed");
    auto graph = ggml_new_graph_custom(ctx, 256, false);
    auto input = ggml_new_tensor_1d(ctx, GGML_TYPE_F32, logits.size());
    ggml_set_input(input);
    llama_sampler_data data = {input, nullptr, nullptr, nullptr};
    sampler->iface->backend_apply(sampler, ctx, graph, &data);
    require(data.logits && data.logits != input, "Sampler did not produce filtered logits");
    ggml_set_output(data.logits);
    ggml_build_forward_expand(graph, data.logits);
    for (int i = 0; i < ggml_graph_n_nodes(graph); ++i) {
        require(ggml_backend_supports_op(metal, ggml_graph_node(graph, i)), "Non-Metal operation");
    }
    auto buffer = ggml_backend_alloc_ctx_tensors(ctx, metal);
    require(buffer, "Metal allocation failed");
    ggml_backend_tensor_set(input, logits.data(), 0, logits.size()*sizeof(float));
    require(ggml_backend_graph_compute(metal, graph) == GGML_STATUS_SUCCESS, "Metal graph failed");
    ggml_backend_synchronize(metal);
    std::vector<float> gpu_logits(logits.size()), after(logits.size());
    ggml_backend_tensor_get(data.logits, gpu_logits.data(), 0, gpu_logits.size()*sizeof(float));
    ggml_backend_tensor_get(input, after.data(), 0, after.size()*sizeof(float));
    require(std::memcmp(logits.data(), after.data(), logits.size()*sizeof(float)) == 0, "Input bytes changed");
    std::vector<int> gpu_ids;
    for (size_t i = 0; i < gpu_logits.size(); ++i) {
        require(!std::isnan(gpu_logits[i]), "Unexpected NaN");
        if (std::isfinite(gpu_logits[i])) {
            require(gpu_logits[i] == logits[i], "Retained logit changed");
            gpu_ids.push_back(int(i));
        } else {
            require(gpu_logits[i] < 0, "Unexpected positive infinity");
        }
    }
    std::sort(cpu_ids.begin(), cpu_ids.end());
    require(!cpu_ids.empty() && !gpu_ids.empty() && cpu_ids[0] == 0 && gpu_ids[0] == 0, "Maximum excluded");
    const bool equal = cpu_ids == gpu_ids;
    json result = {{"p", p}, {"sorted", sorted}, {"boundary", boundary}, {"threshold", threshold},
                   {"input_logits", logits}, {"cpu_retained_ids", cpu_ids}, {"metal_retained_ids", gpu_ids},
                   {"identical_eligibility", equal}, {"input_bytes_preserved", true}, {"all_ops_supported_on_metal", true},
                   {"graph_nodes", ggml_graph_n_nodes(graph)}, {"outputs", logits.size()}};
    ggml_backend_buffer_free(buffer);
    ggml_free(ctx);
    llama_sampler_free(sampler);
    return result;
}

int main() {
    std::setvbuf(stdout, nullptr, _IOLBF, 0);
    try {
        auto metal = ggml_backend_metal_init();
        require(metal, "Metal unavailable");
        int cases = 0, mismatches = 0;
        for (float p : {0.5f, 0.05f}) for (bool sorted : {false, true}) for (bool boundary : {false, true}) {
            const auto result = run_case(metal, p, sorted, boundary);
            printf("M5_SAMPLING_CASE %s\n", result.dump().c_str());
            mismatches += !result.at("identical_eligibility").get<bool>();
            ++cases;
        }
        printf("M5_SAMPLING_DONE %s\n", json({{"cases", cases}, {"eligibility_mismatches", mismatches},
               {"models_loaded", false}, {"timings_measured", false}}).dump().c_str());
        ggml_backend_free(metal);
        return 0;
    } catch (const std::exception & error) {
        fprintf(stderr, "M5_SAMPLING_ERROR %s\n", error.what());
        return 1;
    }
}
