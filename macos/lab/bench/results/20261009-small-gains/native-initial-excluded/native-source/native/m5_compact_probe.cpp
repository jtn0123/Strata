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
static uint64_t (*compact_tiles_count)(void) = nullptr;

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
    bool terminal_only = true;
    bool gate_f32() const { return precision_f32 || mixed_precision == 1; }
    bool up_f32() const { return precision_f32 || mixed_precision == 2; }
    bool down_f32() const { return precision_f32 || mixed_precision != 0; }
    std::string precision_name() const {
        if (layout == "precision-f16") return "all-f16";
        return precision_f32 ? "all-f32" : mixed_precision == 1 ? "gate-f32-up-default" :
               mixed_precision == 2 ? "gate-default-up-f32" : "default";
    }
    int eligible_mm_per_block() const {
        if (rows < 32 || rows > 512 || layout == "unsupported-shape" || layout == "precision-f16") return 0;
        if (layout == "unsupported-k" || layout == "activation-f16") return 1;
        return 3;
    }
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
            result.push_back({rows, 512, "mixed", "plain", false, 0, false});
            result.push_back({rows, 512, "mixed", "plain", true});
            result.push_back({rows, 512, "mixed", "plain", false, 1});
            result.push_back({rows, 512, "mixed", "plain", false, 2});
            for (const std::string layout : {"different-input", "different-ids", "intervening-gate-scale", "activation-unfused"})
                result.push_back({rows, 512, "mixed", layout});
            for (const std::string layout : {"unsupported-shape", "unsupported-k", "activation-f16", "precision-f16"})
                result.push_back({rows, 512, "mixed", layout});
        }
        result.push_back({1, 10, "shared"});
        for (int rows : {33, 64, 127, 508, 512})
            for (int width : {10, 512}) result.push_back({rows, width, "skewed"});
        for (int rows : {508, 512})
            for (int width : {10, 512}) {
                result.push_back({rows, width, "capacity"});
                result.push_back({rows, width, "capacity-permuted"});
            }
    }
    return result;
}

struct ids_input { ggml_tensor * storage; int block, offset; };
struct named_output { std::string name; ggml_tensor * tensor; };

static bool eligible_mm_id(const ggml_tensor * mm) {
    const auto * weight = mm->src[0], * activation = mm->src[1], * ids = mm->src[2];
    const bool gate_up = weight->ne[0] == EMBED && weight->ne[1] == HIDDEN && activation->ne[1] == 1;
    const bool down = weight->ne[0] == HIDDEN && weight->ne[1] == EMBED && activation->ne[1] == SELECTED;
    const int32_t source_precision = mm->op_params[3];
    return mm->op == GGML_OP_MUL_MAT_ID && weight->type == GGML_TYPE_Q2_0 && activation->type == GGML_TYPE_F32 &&
        ids->type == GGML_TYPE_I32 && mm->type == GGML_TYPE_F32 && (gate_up || down) &&
        weight->ne[2] == EXPERTS && weight->ne[3] == 1 && activation->ne[0] == weight->ne[0] &&
        activation->ne[2] >= 32 && activation->ne[2] <= 512 && activation->ne[3] == 1 &&
        ids->ne[0] == SELECTED && ids->ne[1] == activation->ne[2] && ids->ne[2] == 1 && ids->ne[3] == 1 &&
        ids->nb[0] == sizeof(int32_t) && ids->nb[1] >= SELECTED*sizeof(int32_t) && ids->nb[1] % sizeof(int32_t) == 0 &&
        ggml_is_contiguous(weight) && ggml_is_contiguous(activation) && ggml_is_contiguous(mm) && !mm->view_src &&
        (source_precision == GGML_PREC_DEFAULT || source_precision == GGML_PREC_F32);
}

static std::vector<int32_t> make_ids(const case_spec & spec, int block, int phase, int extra_offset) {
    std::vector<int32_t> result(size_t(spec.id_width)*spec.rows, -12345);
    const int shift = (block*61 + phase*37 + extra_offset) % EXPERTS;
    std::vector<int> capacity_ids;
    if (spec.route == "capacity" || spec.route == "capacity-permuted") {
        // Every expert is nonempty. Counts 1 and 33 maximize ceiling(count/32),
        // with the remaining <=31 memberships leaving the tile total unchanged.
        const int extra_tiles = (SELECTED*spec.rows - EXPERTS)/32;
        require(extra_tiles > SELECTED && extra_tiles < EXPERTS, "Capacity fixture out of range");
        std::array<int, EXPERTS> remaining{};
        remaining.fill(1);
        for (int expert = 0; expert < extra_tiles; ++expert) remaining[expert] = 33;
        remaining[extra_tiles] += (SELECTED*spec.rows - EXPERTS) % 32;
        for (int row = 0; row < spec.rows; ++row) {
            std::array<int, EXPERTS> order{};
            for (int expert = 0; expert < EXPERTS; ++expert) order[expert] = expert;
            std::stable_sort(order.begin(), order.end(), [&](int a, int b) { return remaining[a] > remaining[b]; });
            for (int lane = 0; lane < SELECTED; ++lane) {
                const int expert = order[lane];
                require(remaining[expert] > 0, "Capacity degree sequence cannot fill token");
                --remaining[expert]; capacity_ids.push_back(expert);
            }
        }
        require(std::all_of(remaining.begin(), remaining.end(), [](int count) { return count == 0; }),
                "Capacity fixture degree sequence is incomplete");
        require(capacity_ids.size() == size_t(SELECTED)*spec.rows, "Capacity fixture membership count differs");
    }
    for (int row = 0; row < spec.rows; ++row) {
        std::set<int> seen;
        for (int e = 0; e < SELECTED; ++e) {
            int id = 0;
            if (spec.route == "uniform") id = (10*row + e + shift) % EXPERTS;
            else if (spec.route == "shared") id = (e + shift) % EXPERTS;
            else if (spec.route == "mixed") {
                const int unshifted = e < 5 ? e : 5 + ((5*row + e - 5) % 507);
                id = (unshifted + shift) % EXPERTS;
            } else if (spec.route == "skewed") {
                // Include counts 0,1,31,32,33,T while keeping every token's top10 distinct.
                std::vector<int> selected{0};
                if (row < 1) selected.push_back(1);
                if (row < 31) selected.push_back(2);
                if (row < 32) selected.push_back(3);
                if (row < 33) selected.push_back(4);
                for (int lane = 0; selected.size() < SELECTED; ++lane)
                    selected.push_back(5 + ((SELECTED*row + lane) % 506));
                id = (selected[e] + shift) % EXPERTS;
            } else if (spec.route == "capacity" || spec.route == "capacity-permuted") {
                const int lane = spec.route == "capacity-permuted" ? (3*e + 7) % SELECTED : e;
                const int unshifted = capacity_ids[size_t(row)*SELECTED + lane];
                id = ((spec.route == "capacity-permuted" ? (73*unshifted + 19) % EXPERTS : unshifted) + shift) % EXPERTS;
            } else throw std::runtime_error("Unknown synthetic route");
            require(id >= 0 && id < EXPERTS && seen.insert(id).second, "Invalid top10 expert IDs");
            result[size_t(row)*spec.id_width + e] = id;
        }
    }
    return result;
}

static json route_receipt(const std::vector<int32_t> & ids, const case_spec & spec) {
    std::array<int, EXPERTS> counts{};
    for (int row = 0; row < spec.rows; ++row)
        for (int lane = 0; lane < SELECTED; ++lane) ++counts[ids[size_t(row)*spec.id_width + lane]];
    int tiles = 0;
    for (int count : counts) tiles += (count + 31)/32;
    const int bound = (SELECTED*spec.rows + 31*EXPERTS)/32;
    require(tiles <= bound, "Route fixture exceeds proven tile bound");
    if (spec.route == "skewed")
        for (int count : {0, 1, 31, 32, 33, spec.rows})
            require(std::find(counts.begin(), counts.end(), count) != counts.end(), "Skewed fixture lost a tile boundary count");
    if (spec.route == "capacity" || spec.route == "capacity-permuted")
        require(tiles == bound, "Capacity fixture does not attain static tile bound");
    return {{"expert_counts", counts}, {"memberships", SELECTED*spec.rows}, {"nonempty_tiles32", tiles},
            {"static_tile_capacity", bound}, {"distinct_top10_per_token", true}};
}

static void emit(std::ofstream & evidence, const char * marker, const json & value) {
    const auto text = value.dump();
    evidence << text << '\n'; evidence.flush();
    require(bool(evidence), "Evidence write failed");
    std::printf("%s %s\n", marker, text.c_str());
}

static size_t run_case(backends & backend, weight_set & weights, const case_spec & spec,
                       bool perf, bool compact, std::ofstream & evidence) {
    const int copies = 2;
    graph_owner owner;
    owner.ctx = ggml_init({ggml_tensor_overhead()*GRAPH_SIZE + ggml_graph_overhead_custom(GRAPH_SIZE, false), nullptr, true});
    require(owner.ctx, "Graph context unavailable");
    owner.input_ctx = ggml_init({ggml_tensor_overhead()*32, nullptr, true});
    require(owner.input_ctx, "Input context unavailable");
    auto * ctx = owner.ctx;
    auto * graph = ggml_new_graph_custom(ctx, GRAPH_SIZE, false);
    auto * input = ggml_new_tensor_3d(owner.input_ctx, GGML_TYPE_F32, EMBED, 1, spec.rows);
    ggml_set_input(input); ggml_set_name(input, "compact.input");
    std::vector<ggml_tensor *> leaves{input};
    std::vector<ids_input> ids_inputs;
    std::vector<named_output> outputs;
    json projections = json::array();
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
        const int k = spec.layout == "unsupported-k" ? EMBED - 64 : EMBED;
        const int hidden = spec.layout == "unsupported-shape" ? HIDDEN - 64 : HIDDEN;
        auto slice_weight = [&](int family, int columns, int rows) {
            auto * weight = weights.values[family].tensor;
            if (columns == weight->ne[0] && rows == weight->ne[1]) return weight;
            // Stock Metal supports strided Q2_0 MM_ID weights, but Q2_0-to-Q2_0
            // CONT is unsupported. These fallback cases exercise shape and stride
            // guards jointly; they do not isolate either guard on its own.
            return ggml_view_3d(ctx, weight, columns, rows, EXPERTS, weight->nb[1], weight->nb[2], 0);
        };
        auto slice_input = [&](ggml_tensor * value) {
            return k == EMBED ? value : ggml_cont(ctx, ggml_view_3d(ctx, value, k, 1, spec.rows, value->nb[1], value->nb[2], 0));
        };
        auto * gate_x = slice_input(x);
        up_x = slice_input(up_x);
        if (spec.layout == "activation-f16") {
            gate_x = ggml_cast(ctx, gate_x, GGML_TYPE_F16); up_x = ggml_cast(ctx, up_x, GGML_TYPE_F16);
        }
        auto * gate = ggml_mul_mat_id(ctx, slice_weight(0, k, hidden), gate_x, ids);
        auto * up = ggml_mul_mat_id(ctx, slice_weight(1, k, hidden), up_x, up_ids);
        auto * gate_arg = spec.layout == "intervening-gate-scale" ? ggml_scale(ctx, gate, 1.125f) : gate;
        auto * activated = spec.layout == "activation-unfused" ? ggml_mul(ctx, ggml_silu(ctx, gate_arg), up) :
                                                               ggml_swiglu_split(ctx, gate_arg, up);
        auto * down = ggml_mul_mat_id(ctx, slice_weight(2, hidden, EMBED), activated, ids);
        if (spec.gate_f32()) require(ggml_prec_set_src(gate, GGML_PREC_F32, 1), "Gate F32 source precision unavailable");
        if (spec.up_f32()) require(ggml_prec_set_src(up, GGML_PREC_F32, 1), "Up F32 source precision unavailable");
        if (spec.down_f32()) require(ggml_prec_set_src(down, GGML_PREC_F32, 1), "Down F32 source precision unavailable");
        if (spec.layout == "precision-f16")
            for (auto * mm : {gate, up, down}) require(ggml_prec_set_src(mm, GGML_PREC_F16, 1), "F16 source precision unavailable");
        const std::string name = "block" + std::to_string(block) + ".";
        int eligible_count = 0;
        for (const auto & entry : std::vector<named_output>{{name + "gate", gate}, {name + "up", up}, {name + "down", down}}) {
            const auto * mm = entry.tensor;
            const bool eligible = eligible_mm_id(mm);
            eligible_count += eligible;
            projections.push_back({{"name", entry.name}, {"eligible", eligible},
                {"weight_shape", {mm->src[0]->ne[0], mm->src[0]->ne[1], mm->src[0]->ne[2], mm->src[0]->ne[3]}},
                {"activation_shape", {mm->src[1]->ne[0], mm->src[1]->ne[1], mm->src[1]->ne[2], mm->src[1]->ne[3]}},
                {"activation_type", ggml_type_name(mm->src[1]->type)}, {"weight_type", ggml_type_name(mm->src[0]->type)},
                {"source_precision", mm->op_params[3]}, {"id_stride_bytes", mm->src[2]->nb[1]},
                {"weight_contiguous", ggml_is_contiguous(mm->src[0])}, {"activation_contiguous", ggml_is_contiguous(mm->src[1])},
                {"output_contiguous", ggml_is_contiguous(mm)}});
        }
        require(eligible_count == spec.eligible_mm_per_block(), "Per-MM fixture predicate disagrees with graph tensors");
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
        if (block + 1 == copies) keep(name + "residual", previous);
    }
    ggml_build_forward_expand(graph, previous);
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
            // Mixed precision includes a DEFAULT conversion in both dependent blocks.
            // Keep its input bounded so block1 does not overflow that block2 conversion.
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
        const uint64_t before = compact_tiles_count ? compact_tiles_count() : 0;
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
        const uint64_t after = compact_tiles_count ? compact_tiles_count() : 0;
        require(after >= before, "Compact counter moved backwards");
        const uint64_t delta = after - before;
        const uint64_t eligible_mm = uint64_t(copies)*spec.eligible_mm_per_block();
        require(delta == (compact ? executions*eligible_mm : 0), "Incomplete eligible compact MM_ID or fallback coverage");
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
        json ids_hashes = json::array(), routes = json::array();
        for (size_t i = 0; i < ids_inputs.size(); ++i) {
            std::vector<int32_t> data(ids_values[i].size());
            ggml_backend_tensor_get(ids_inputs[i].storage, data.data(), 0, data.size()*4);
            require(data == ids_values[i], "ID values or padding changed");
            ids_hashes.push_back(hash_bytes(data.data(), data.size()*4));
            routes.push_back(route_receipt(data, spec));
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
        json receipt = {{"id", spec.id()}, {"mode", perf ? "perf" : "check"}, {"scope", compact ? "compact" : "control"},
            {"rows", spec.rows}, {"route", spec.route}, {"route_source", "synthetic"}, {"layout", spec.layout},
            {"id_stride_bytes", spec.id_width*4}, {"precision", spec.precision_name()},
            {"terminal_only", spec.terminal_only},
            {"projection_precision", {{"gate", spec.gate_f32() ? "f32" : "default"},
                                       {"up", spec.up_f32() ? "f32" : "default"},
                                       {"down", spec.down_f32() ? "f32" : "default"}}},
            {"round", round}, {"input_version", phase}, {"same_graph_mutation", !perf}, {"triplets_per_graph", copies},
            {"eligible", spec.eligible_mm_per_block() > 0}, {"eligible_mm_per_graph", eligible_mm},
            {"mm_ids_per_graph", copies*3}, {"projections", projections},
            {"counter_available", compact_tiles_count != nullptr}, {"count_delta", delta},
            {"counter_semantics", "each eligible encoded compact MM_ID; elapsed complete graph measured separately"}, {"executions", executions},
            {"outputs", output_receipts}, {"output_sha256", output_receipts.back().at("sha256")},
            {"input_sha256", hash_bytes(values.data(), values.size()*4)}, {"ids_sha256", ids_hashes}, {"routes", routes},
            {"coefficients_sha256", hash_bytes(coefficients.data(), coefficients.size()*4)}, {"weights", weights.receipts()},
            {"inputs_preserved", true}, {"ids_preserved", true}, {"all_nodes_metal", true}, {"scheduler_splits", 1},
            {"cpu_compute_nodes", 0}, {"evaluation_callbacks", false}, {"exact_oracle", "original-engine full F32 byte digests"},
            {"pipeline_primed", perf}, {"warmup_ns", warmup_ns}, {"warmup_iterations", warmup_iterations},
            {"block_ns", block_ns}, {"block_iterations", block_iterations}, {"ns_samples", ns_samples},
            {"ns_per_triplet", ns_per_triplet}, {"median_ns", perf ? sorted[sorted.size()/2] : 0.0},
            {"graph_buffer_bytes", graph_bytes}, {"input_buffer_bytes", input_bytes},
            {"allocation_estimate_bytes", 2*weights.bytes + graph_bytes + input_bytes},
            {"performance_outputs", perf || spec.terminal_only ? "terminal residual only; inputs allocated separately" : "all projections and residual"}};
        emit(evidence, "M5_COMPACT_CASE", receipt); ++emitted;
    }
    return emitted;
}

int main(int argc, char ** argv) {
    std::setvbuf(stdout, nullptr, _IOLBF, 0);
    try {
        require(argc == 4, "Usage: compact-probe check|perf outputs.jsonl control|compact");
        const std::string mode = argv[1], scope = argv[3];
        require(mode == "check" || mode == "perf", "Unknown mode");
        require(scope == "control" || scope == "compact", "Unknown scope");
        const bool perf = mode == "perf", compact = scope == "compact";
        std::ofstream evidence(argv[2]); require(bool(evidence), "Evidence file unavailable");
        backends backend; backend.init();
        compact_tiles_count = reinterpret_cast<uint64_t (*)(void)>(ggml_backend_reg_get_proc_address(
            ggml_backend_dev_backend_reg(ggml_backend_get_device(backend.metal)), "ggml_metal_lab_compact_tiles_count"));
        require(!compact || compact_tiles_count, "Candidate compact counter unavailable");
        weight_set weights; weights.init(backend.metal);
        const auto cases = inventory(perf);
        size_t records = 0;
        for (const auto & spec : cases) {
            std::printf("M5_COMPACT_CASE_BEGIN %s\n", json({{"id", spec.id()}, {"mode", mode}, {"scope", scope}}).dump().c_str());
            records += run_case(backend, weights, spec, perf, compact, evidence);
        }
        weights.verify_preserved();
        emit(evidence, "M5_COMPACT_DONE", {{"mode", mode}, {"scope", scope}, {"fixtures", cases.size()},
            {"cases", records}, {"weights", weights.receipts()}, {"weights_preserved", true},
            {"allocated_weight_bytes", weights.bytes}, {"counter_available", compact_tiles_count != nullptr},
            {"models_loaded", false}, {"route_source", "synthetic"}, {"cpu_reference_values", 0},
            {"forced_overlap_tested", false}, {"partition_edge_tested", false},
            {"exact_oracle", "compare all output digests against separately linked original engine"},
            {"scope_limit", "No model throughput, captured prompt route distribution, or cross-encoder compact claim"}});
        return 0;
    } catch (const std::exception & error) {
        std::fprintf(stderr, "M5_COMPACT_ERROR %s\n", error.what());
        return 1;
    }
}
