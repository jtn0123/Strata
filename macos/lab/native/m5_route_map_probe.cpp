// Full prompt MoE blocks; original-engine F32 byte digests are the exact oracle.
#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-alloc.h"
#include <nlohmann/json.hpp>
#include <CommonCrypto/CommonDigest.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <limits>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using json = nlohmann::json;
using clock_type = std::chrono::steady_clock;
static constexpr int EMBED = 2560, HIDDEN = 640, EXPERTS = 512, SELECTED = 10;
static constexpr size_t GRAPH_SIZE = 512;
static uint64_t (*route_map_count)(void) = nullptr;

static void require(bool ok, const char * message) {
    if (!ok) throw std::runtime_error(message);
}

static uint32_t next_random(uint32_t & state) {
    state ^= state << 13; state ^= state >> 17; state ^= state << 5;
    return state;
}

static uint64_t elapsed_ns(clock_type::time_point start) {
    return uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(clock_type::now() - start).count());
}

static std::string hash_bytes(const void * data, size_t bytes) {
    require(bytes <= std::numeric_limits<CC_LONG>::max(), "Digest input too large");
    unsigned char raw[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(data, CC_LONG(bytes), raw);
    char result[65];
    for (size_t i = 0; i < sizeof(raw); ++i) std::snprintf(result + 2*i, 3, "%02x", raw[i]);
    return result;
}

struct backends {
    ggml_backend_t metal = nullptr, cpu = nullptr;
    ~backends() {
        if (cpu) ggml_backend_free(cpu);
        if (metal) ggml_backend_free(metal);
    }
    void init() {
        ggml_backend_load_all();
        metal = ggml_backend_init_by_name("MTL0", nullptr);
        cpu = ggml_backend_init_by_type(GGML_BACKEND_DEVICE_TYPE_CPU, nullptr);
        require(metal && cpu, "Required backends unavailable");
    }
};

struct packed_weight {
    ggml_tensor * tensor = nullptr;
    std::vector<uint8_t> bytes;
    std::string hash;
};

struct weight_set {
    ggml_context * ctx = nullptr;
    ggml_backend_buffer_t buffer = nullptr;
    std::array<packed_weight, 3> values;
    size_t bytes = 0;
    ~weight_set() {
        if (buffer) ggml_backend_buffer_free(buffer);
        if (ctx) ggml_free(ctx);
    }
    void init(ggml_backend_t metal) {
        require(ggml_blck_size(GGML_TYPE_Q2_0) == 64 && ggml_type_size(GGML_TYPE_Q2_0) == 18,
                "Q2_0 block ABI differs");
        ctx = ggml_init({ggml_tensor_overhead()*16, nullptr, true});
        require(ctx, "Weight context unavailable");
        const char * names[] = {"gate.weight", "up.weight", "down.weight"};
        for (int family = 0; family < 3; ++family) {
            auto & weight = values[family];
            const int k = family == 2 ? HIDDEN : EMBED, m = family == 2 ? EMBED : HIDDEN;
            weight.tensor = ggml_new_tensor_3d(ctx, GGML_TYPE_Q2_0, k, m, EXPERTS);
            ggml_set_name(weight.tensor, names[family]);
            weight.bytes.resize(ggml_nbytes(weight.tensor));
            uint32_t state = 0x278291u + uint32_t(family)*7919u;
            // Q2_0 stores a finite half scale and sixteen arbitrary packed 2-bit bytes.
            for (size_t offset = 0; offset < weight.bytes.size(); offset += 18) {
                const auto scale = ggml_fp32_to_fp16(std::ldexp(float(16 + (next_random(state) & 15)), -11));
                std::memcpy(weight.bytes.data() + offset, &scale, sizeof(scale));
                for (int i = 2; i < 18; i += 4) {
                    const uint32_t bits = next_random(state);
                    std::memcpy(weight.bytes.data() + offset + i, &bits, sizeof(bits));
                }
            }
            weight.hash = hash_bytes(weight.bytes.data(), weight.bytes.size());
            bytes += weight.bytes.size();
        }
        buffer = ggml_backend_alloc_ctx_tensors(ctx, metal);
        require(buffer, "Weight allocation failed");
        ggml_backend_buffer_set_usage(buffer, GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
        for (auto & weight : values)
            ggml_backend_tensor_set(weight.tensor, weight.bytes.data(), 0, weight.bytes.size());
    }
    json receipts() const {
        json result = json::array();
        for (const auto & weight : values)
            result.push_back({{"name", ggml_get_name(weight.tensor)}, {"bytes", weight.bytes.size()},
                              {"sha256", weight.hash}, {"experts", EXPERTS},
                              {"k", weight.tensor->ne[0]}, {"m", weight.tensor->ne[1]}});
        return result;
    }
    void verify_preserved() const {
        std::vector<uint8_t> chunk(8*1024*1024);
        for (const auto & weight : values) {
            require(hash_bytes(weight.bytes.data(), weight.bytes.size()) == weight.hash, "Host weight bytes changed");
            for (size_t offset = 0; offset < weight.bytes.size(); offset += chunk.size()) {
                const size_t size = std::min(chunk.size(), weight.bytes.size() - offset);
                ggml_backend_tensor_get(weight.tensor, chunk.data(), offset, size);
                require(std::memcmp(chunk.data(), weight.bytes.data() + offset, size) == 0, "Device weight bytes changed");
            }
        }
    }
};

struct graph_owner {
    ggml_context * ctx = nullptr;
    ggml_context * input_ctx = nullptr;
    ggml_backend_buffer_t input_buffer = nullptr;
    ggml_backend_sched_t sched = nullptr;
    ~graph_owner() {
        if (sched) { ggml_backend_sched_synchronize(sched); ggml_backend_sched_free(sched); }
        if (ctx) ggml_free(ctx);
        if (input_buffer) ggml_backend_buffer_free(input_buffer);
        if (input_ctx) ggml_free(input_ctx);
    }
};

struct case_spec {
    int rows, id_width;
    std::string route, layout = "plain";
    bool precision_f32 = false;
    int mixed_precision = 0;
    bool terminal_only = false;
    bool gate_f32() const { return precision_f32 || mixed_precision == 1; }
    bool up_f32() const { return precision_f32 || mixed_precision == 2; }
    bool down_f32() const { return precision_f32 || mixed_precision != 0; }
    std::string precision_name() const {
        return precision_f32 ? "all-f32" : mixed_precision == 1 ? "gate-f32-up-default" :
               mixed_precision == 2 ? "gate-default-up-f32" : "default";
    }
    bool eligible() const { return rows >= 32 && rows <= 512 && layout == "plain"; }
    std::string id() const {
        return "t" + std::to_string(rows) + "-" + route + "-stride" + std::to_string(id_width*4) +
               "-" + layout + "-precision-" + precision_name() + (terminal_only ? "-terminal-only" : "");
    }
};

static std::vector<case_spec> inventory(bool perf) {
    std::vector<case_spec> result;
    if (perf) {
        for (int rows : {32, 33, 64, 127, 508, 512})
            for (const std::string route : {"uniform", "shared", "mixed"}) result.push_back({rows, 512, route});
    } else {
        for (int rows : {31, 32, 33, 64, 127, 508, 512, 513})
            for (const std::string route : {"uniform", "shared", "mixed"})
                for (int width : {10, 512}) result.push_back({rows, width, route});
        for (int rows : {33, 512}) {
            result.push_back({rows, 512, "mixed", "plain", true});
            result.push_back({rows, 512, "mixed", "plain", false, 1});
            result.push_back({rows, 512, "mixed", "plain", false, 2});
            result.push_back({rows, 512, "mixed", "plain", false, 1, true});
            result.push_back({rows, 512, "mixed", "plain", false, 2, true});
            for (const std::string layout : {"different-input", "different-ids", "intervening-gate-scale", "activation-unfused"})
                result.push_back({rows, 512, "mixed", layout});
        }
    }
    return result;
}

struct ids_input { ggml_tensor * storage; int block, offset; };
struct named_output { std::string name; ggml_tensor * tensor; };

static std::vector<int32_t> make_ids(const case_spec & spec, int block, int phase, int extra_offset) {
    std::vector<int32_t> result(size_t(spec.id_width)*spec.rows, -12345);
    const int shift = (block*61 + phase*37 + extra_offset) % EXPERTS;
    for (int row = 0; row < spec.rows; ++row) {
        std::set<int> seen;
        for (int e = 0; e < SELECTED; ++e) {
            int id = 0;
            if (spec.route == "uniform") id = (10*row + e + shift) % EXPERTS;
            else if (spec.route == "shared") id = (e + shift) % EXPERTS;
            else if (spec.route == "mixed") {
                const int unshifted = e < 5 ? e : 5 + ((5*row + e - 5) % 507);
                id = (unshifted + shift) % EXPERTS;
            } else throw std::runtime_error("Unknown synthetic route");
            require(id >= 0 && id < EXPERTS && seen.insert(id).second, "Invalid top10 expert IDs");
            result[size_t(row)*spec.id_width + e] = id;
        }
    }
    return result;
}

static void emit(std::ofstream & evidence, const char * marker, const json & value) {
    const auto text = value.dump();
    evidence << text << '\n'; evidence.flush();
    require(bool(evidence), "Evidence write failed");
    std::printf("%s %s\n", marker, text.c_str());
}

static size_t run_case(backends & backend, weight_set & weights, const case_spec & spec,
                       bool perf, bool reuse, std::ofstream & evidence) {
    const int copies = perf ? 2 : 1;
    graph_owner owner;
    owner.ctx = ggml_init({ggml_tensor_overhead()*GRAPH_SIZE + ggml_graph_overhead_custom(GRAPH_SIZE, false), nullptr, true});
    require(owner.ctx, "Graph context unavailable");
    owner.input_ctx = ggml_init({ggml_tensor_overhead()*32, nullptr, true});
    require(owner.input_ctx, "Input context unavailable");
    auto * ctx = owner.ctx;
    auto * graph = ggml_new_graph_custom(ctx, GRAPH_SIZE, false);
    auto * input = ggml_new_tensor_3d(owner.input_ctx, GGML_TYPE_F32, EMBED, 1, spec.rows);
    ggml_set_input(input); ggml_set_name(input, "route_map.input");
    std::vector<ggml_tensor *> leaves{input};
    std::vector<ids_input> ids_inputs;
    std::vector<named_output> outputs;
    ggml_tensor * previous = input;
    auto keep = [&](const std::string & name, ggml_tensor * tensor) {
        ggml_set_name(tensor, name.c_str()); ggml_set_output(tensor); outputs.push_back({name, tensor});
    };
    auto add_ids = [&](int block, int offset) {
        auto * storage = ggml_new_tensor_2d(owner.input_ctx, GGML_TYPE_I32, spec.id_width, spec.rows);
        ggml_set_input(storage); leaves.push_back(storage);
        ids_inputs.push_back({storage, block, offset});
        return ggml_view_2d(ctx, storage, SELECTED, spec.rows, size_t(spec.id_width)*4, 0);
    };
    for (int block = 0; block < copies; ++block) {
        auto * x = previous;
        auto * ids = add_ids(block, 0);
        auto * up_ids = spec.layout == "different-ids" ? add_ids(block, 7) : ids;
        auto * up_x = spec.layout == "different-input" ? ggml_scale(ctx, x, 1.125f) : x;
        auto * gate = ggml_mul_mat_id(ctx, weights.values[0].tensor, x, ids);
        auto * up = ggml_mul_mat_id(ctx, weights.values[1].tensor, up_x, up_ids);
        auto * gate_arg = spec.layout == "intervening-gate-scale" ? ggml_scale(ctx, gate, 1.125f) : gate;
        auto * activated = spec.layout == "activation-unfused" ? ggml_mul(ctx, ggml_silu(ctx, gate_arg), up) :
                                                               ggml_swiglu_split(ctx, gate_arg, up);
        auto * down = ggml_mul_mat_id(ctx, weights.values[2].tensor, activated, ids);
        if (spec.gate_f32()) require(ggml_prec_set_src(gate, GGML_PREC_F32, 1), "Gate F32 source precision unavailable");
        if (spec.up_f32()) require(ggml_prec_set_src(up, GGML_PREC_F32, 1), "Up F32 source precision unavailable");
        if (spec.down_f32()) require(ggml_prec_set_src(down, GGML_PREC_F32, 1), "Down F32 source precision unavailable");
        const std::string name = "block" + std::to_string(block) + ".";
        if (!perf && !spec.terminal_only) {
            keep(name + "gate", gate); keep(name + "up", up);
            keep(name + "activated", activated); keep(name + "down", down);
        }
        auto * coefficients = ggml_new_tensor_3d(owner.input_ctx, GGML_TYPE_F32, 1, SELECTED, spec.rows);
        ggml_set_input(coefficients); leaves.push_back(coefficients);
        auto * weighted = ggml_mul(ctx, down, coefficients);
        auto * sum = ggml_view_2d(ctx, weighted, EMBED, spec.rows, weighted->nb[2], 0);
        for (int e = 1; e < SELECTED; ++e)
            sum = ggml_add(ctx, sum, ggml_view_2d(ctx, weighted, EMBED, spec.rows, weighted->nb[2], size_t(e)*weighted->nb[1]));
        previous = ggml_add(ctx, x, ggml_reshape_3d(ctx, sum, EMBED, 1, spec.rows));
        if (!perf || block + 1 == copies) keep(name + "residual", previous);
    }
    ggml_build_forward_expand(graph, previous);
    if (!perf) require(ggml_graph_n_nodes(graph) <= 64, "Check fixture must stay in one encoding partition");
    // Inputs have their own allocation; only requested evidence outputs pin graph temporaries.
    owner.input_buffer = ggml_backend_alloc_ctx_tensors(owner.input_ctx, backend.metal);
    require(owner.input_buffer, "Input allocation failed");
    ggml_backend_t list[] = {backend.metal, backend.cpu};
    owner.sched = ggml_backend_sched_new(list, nullptr, 2, GRAPH_SIZE, false, true);
    require(owner.sched, "Scheduler unavailable");
    for (auto * tensor : leaves) ggml_backend_sched_set_tensor_backend(owner.sched, tensor, backend.metal);
    for (int i = 0; i < ggml_graph_n_nodes(graph); ++i)
        ggml_backend_sched_set_tensor_backend(owner.sched, ggml_graph_node(graph, i), backend.metal);
    require(ggml_backend_sched_alloc_graph(owner.sched, graph), "Graph allocation failed");

    auto verify_placement = [&]() {
        require(ggml_backend_sched_get_n_splits(owner.sched) == 1, "Expected one Metal scheduler split");
        auto storage_is_metal = [&](ggml_tensor * tensor) {
            while (tensor->view_src) tensor = tensor->view_src;
            require(tensor->buffer && ggml_backend_buffer_get_type(tensor->buffer) == ggml_backend_get_default_buffer_type(backend.metal),
                    "Tensor storage is not the actual Metal buffer");
        };
        for (int i = 0; i < ggml_graph_n_nodes(graph); ++i) {
            auto * node = ggml_graph_node(graph, i);
            require(ggml_backend_sched_get_tensor_backend(owner.sched, node) == backend.metal, "Unexpected CPU graph placement");
            storage_is_metal(node);
            for (auto * source : node->src) if (source) storage_is_metal(source);
        }
        for (auto * tensor : leaves) storage_is_metal(tensor);
    };
    auto compute = [&]() {
        require(ggml_backend_sched_graph_compute(owner.sched, graph) == GGML_STATUS_SUCCESS, "Scheduled compute failed");
        ggml_backend_sched_synchronize(owner.sched);
    };
    json original_outputs;
    size_t emitted = 0;
    for (int round = 0; round < (perf ? 1 : 3); ++round) {
        const int phase = round == 1 ? 1 : 0;
        std::vector<float> values(size_t(EMBED)*spec.rows);
        uint32_t state = 0x815913u + uint32_t(phase)*9029u;
        for (float & value : values) {
            value = float(int(next_random(state) % 200001u) - 100000)/100000.0f;
            if (spec.precision_f32) value *= 262144.0f;
            else if (spec.mixed_precision) value *= 60000.0f;
        }
        ggml_backend_tensor_set(input, values.data(), 0, values.size()*4);
        std::vector<std::vector<int32_t>> ids_values;
        for (const auto & entry : ids_inputs) {
            ids_values.push_back(make_ids(spec, entry.block, phase, entry.offset));
            ggml_backend_tensor_set(entry.storage, ids_values.back().data(), 0, ids_values.back().size()*4);
        }
        const std::vector<float> coefficients(size_t(SELECTED)*spec.rows, 0.1f);
        for (auto * leaf : leaves)
            if (leaf != input && leaf->type == GGML_TYPE_F32)
                ggml_backend_tensor_set(leaf, coefficients.data(), 0, coefficients.size()*4);
        const uint64_t before = route_map_count ? route_map_count() : 0;
        uint64_t executions = 0, warmup_ns = 0, warmup_iterations = 0;
        std::vector<uint64_t> block_ns, block_iterations;
        std::vector<double> ns_samples, ns_per_triplet;
        compute(); ++executions;
        verify_placement(); // Inspect the allocated graph after an actual scheduler computation.
        if (perf) {
            auto start = clock_type::now();
            do { compute(); ++executions; ++warmup_iterations; } while (elapsed_ns(start) < 500000000ULL);
            warmup_ns = elapsed_ns(start);
            for (int block = 0; block < 7; ++block) {
                uint64_t iterations = 0;
                start = clock_type::now();
                do { compute(); ++iterations; ++executions; }
                while (iterations < 8 || elapsed_ns(start) < 100000000ULL);
                const uint64_t ns = elapsed_ns(start);
                block_ns.push_back(ns); block_iterations.push_back(iterations);
                ns_samples.push_back(double(ns)/double(iterations));
                ns_per_triplet.push_back(ns_samples.back()/copies);
            }
            verify_placement();
        }
        const uint64_t after = route_map_count ? route_map_count() : 0;
        require(after >= before, "Route-map counter moved backwards");
        const uint64_t delta = after - before;
        require(delta <= executions*uint64_t(copies), "More borrowed maps than eligible projection pairs");
        if (reuse && spec.eligible()) require(delta == executions*uint64_t(copies), "Incomplete eligible route-map reuse coverage");
        else require(delta == 0, "Unexpected route-map reuse in control or fallback fixture");
        json output_receipts = json::array();
        for (const auto & output : outputs) {
            require(ggml_is_contiguous(output.tensor) && output.tensor->type == GGML_TYPE_F32, "Output evidence layout differs");
            std::vector<float> data(ggml_nelements(output.tensor));
            ggml_backend_tensor_get(output.tensor, data.data(), 0, data.size()*4);
            for (float value : data) require(std::isfinite(value), "Nonfinite full-block output");
            output_receipts.push_back({{"name", output.name}, {"elements", data.size()}, {"bytes", data.size()*4},
                                       {"sha256", hash_bytes(data.data(), data.size()*4)}, {"finite", true}});
        }
        if (round == 0) original_outputs = output_receipts;
        if (round == 2) require(output_receipts == original_outputs, "A/B/A input and ID restoration changed output bits");
        std::vector<float> input_after(values.size());
        ggml_backend_tensor_get(input, input_after.data(), 0, input_after.size()*4);
        require(std::memcmp(input_after.data(), values.data(), values.size()*4) == 0, "Input bytes changed");
        json ids_hashes = json::array();
        for (size_t i = 0; i < ids_inputs.size(); ++i) {
            std::vector<int32_t> data(ids_values[i].size());
            ggml_backend_tensor_get(ids_inputs[i].storage, data.data(), 0, data.size()*4);
            require(data == ids_values[i], "ID values or padding changed");
            ids_hashes.push_back(hash_bytes(data.data(), data.size()*4));
        }
        for (auto * leaf : leaves) if (leaf != input && leaf->type == GGML_TYPE_F32) {
            std::vector<float> data(coefficients.size());
            ggml_backend_tensor_get(leaf, data.data(), 0, data.size()*4);
            require(std::memcmp(data.data(), coefficients.data(), data.size()*4) == 0, "Reduction coefficients changed");
        }
        auto sorted = ns_samples; std::sort(sorted.begin(), sorted.end());
        const size_t graph_bytes = ggml_backend_sched_get_buffer_size(owner.sched, backend.metal);
        const size_t input_bytes = ggml_backend_buffer_get_size(owner.input_buffer);
        require(2*weights.bytes + graph_bytes + input_bytes < 3ULL*1024*1024*1024, "Probe allocation estimate exceeds 3 GiB");
        json receipt = {{"id", spec.id()}, {"mode", perf ? "perf" : "check"}, {"scope", reuse ? "reuse" : "control"},
            {"rows", spec.rows}, {"route", spec.route}, {"route_source", "synthetic"}, {"layout", spec.layout},
            {"id_stride_bytes", spec.id_width*4}, {"precision", spec.precision_name()},
            {"terminal_only", spec.terminal_only},
            {"projection_precision", {{"gate", spec.gate_f32() ? "f32" : "default"},
                                       {"up", spec.up_f32() ? "f32" : "default"},
                                       {"down", spec.down_f32() ? "f32" : "default"}}},
            {"round", round}, {"input_version", phase}, {"same_graph_mutation", !perf}, {"triplets_per_graph", copies},
            {"eligible", spec.eligible()}, {"counter_available", route_map_count != nullptr}, {"count_delta", delta},
            {"counter_semantics", "borrowed map encodings; completed graph checked separately"}, {"executions", executions},
            {"outputs", output_receipts}, {"output_sha256", output_receipts.back().at("sha256")},
            {"input_sha256", hash_bytes(values.data(), values.size()*4)}, {"ids_sha256", ids_hashes},
            {"coefficients_sha256", hash_bytes(coefficients.data(), coefficients.size()*4)}, {"weights", weights.receipts()},
            {"inputs_preserved", true}, {"ids_preserved", true}, {"all_nodes_metal", true}, {"scheduler_splits", 1},
            {"cpu_compute_nodes", 0}, {"evaluation_callbacks", false}, {"exact_oracle", "original-engine full F32 byte digests"},
            {"pipeline_primed", perf}, {"warmup_ns", warmup_ns}, {"warmup_iterations", warmup_iterations},
            {"block_ns", block_ns}, {"block_iterations", block_iterations}, {"ns_samples", ns_samples},
            {"ns_per_triplet", ns_per_triplet}, {"median_ns", perf ? sorted[sorted.size()/2] : 0.0},
            {"graph_buffer_bytes", graph_bytes}, {"input_buffer_bytes", input_bytes},
            {"allocation_estimate_bytes", 2*weights.bytes + graph_bytes + input_bytes},
            {"performance_outputs", perf || spec.terminal_only ? "terminal residual only; inputs allocated separately" : "all projections and residual"}};
        emit(evidence, "M5_ROUTE_MAP_CASE", receipt); ++emitted;
    }
    return emitted;
}

int main(int argc, char ** argv) {
    std::setvbuf(stdout, nullptr, _IOLBF, 0);
    try {
        require(argc == 4, "Usage: route-map-probe check|perf outputs.jsonl control|reuse");
        const std::string mode = argv[1], scope = argv[3];
        require(mode == "check" || mode == "perf", "Unknown mode");
        require(scope == "control" || scope == "reuse", "Unknown scope");
        const bool perf = mode == "perf", reuse = scope == "reuse";
        std::ofstream evidence(argv[2]); require(bool(evidence), "Evidence file unavailable");
        backends backend; backend.init();
        route_map_count = reinterpret_cast<uint64_t (*)(void)>(ggml_backend_reg_get_proc_address(
            ggml_backend_dev_backend_reg(ggml_backend_get_device(backend.metal)), "ggml_metal_lab_route_map_count"));
        require(!reuse || route_map_count, "Candidate route-map counter unavailable");
        weight_set weights; weights.init(backend.metal);
        const auto cases = inventory(perf);
        size_t records = 0;
        for (const auto & spec : cases) {
            std::printf("M5_ROUTE_MAP_CASE_BEGIN %s\n", json({{"id", spec.id()}, {"mode", mode}, {"scope", scope}}).dump().c_str());
            records += run_case(backend, weights, spec, perf, reuse, evidence);
        }
        weights.verify_preserved();
        emit(evidence, "M5_ROUTE_MAP_DONE", {{"mode", mode}, {"scope", scope}, {"fixtures", cases.size()},
            {"cases", records}, {"weights", weights.receipts()}, {"weights_preserved", true},
            {"allocated_weight_bytes", weights.bytes}, {"counter_available", route_map_count != nullptr},
            {"models_loaded", false}, {"route_source", "synthetic"}, {"cpu_reference_values", 0},
            {"forced_overlap_tested", false}, {"partition_edge_tested", false},
            {"exact_oracle", "compare all output digests against separately linked original engine"},
            {"scope_limit", "No model throughput, captured prompt route distribution, or cross-encoder reuse claim"}});
        return 0;
    } catch (const std::exception & error) {
        std::fprintf(stderr, "M5_ROUTE_MAP_ERROR %s\n", error.what());
        return 1;
    }
}
