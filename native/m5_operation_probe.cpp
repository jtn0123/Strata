// Diagnostic driver around the pinned native tester. No backend or shader edits.
// M5_NATIVE_TEST_SOURCE is supplied by scripts/benchmark_m5_ops.py.
#define main m5_original_backend_test_main
#include M5_NATIVE_TEST_SOURCE
#undef main

#include <chrono>
#include <numeric>
#include <stdexcept>
#include <nlohmann/json.hpp>

namespace m5_ops {
using json = nlohmann::json;

void require(bool ok, const char * message) {
    if (!ok) throw std::runtime_error(message);
}

std::vector<int32_t> routing(int rows, const std::string & mode, uint32_t seed) {
    require(rows >= 1 && rows <= 5, "Unsupported token rows");
    require(mode == "independent" || mode == "shared", "Unknown routing scenario");
    std::mt19937 rng(seed);
    std::vector<int32_t> all(512), ids(10 * rows);
    std::iota(all.begin(), all.end(), 0);
    for (int row = 0; row < rows; ++row) {
        if (row == 0 || mode == "independent") std::shuffle(all.begin(), all.end(), rng);
        std::copy_n(all.begin(), 10, ids.begin() + 10 * row);
    }
    return ids;
}

// Small reproducible chunks avoid a multi-GiB temporary float weight array.
void initialize(ggml_tensor * t) {
    require(ggml_is_contiguous(t), "Initializer requires contiguous tensors");
    const int64_t width = t->ne[0];
    const int64_t nrows = ggml_nrows(t);
    const size_t row_bytes = ggml_row_size(t->type, width);
    std::vector<float> values(64 * width);
    std::vector<uint8_t> packed(64 * row_bytes);
    uint64_t state = 0x123456789abcdefULL + width + nrows;
    for (int64_t row = 0; row < nrows; row += 64) {
        const int64_t count = std::min<int64_t>(64, nrows - row);
        for (int64_t i = 0; i < count * width; ++i) {
            state ^= state >> 12; state ^= state << 25; state ^= state >> 27;
            const uint64_t bits = state * 2685821657736338717ULL;
            values[i] = float(int32_t(bits >> 40) - 8388608) / 8388608.0f;
        }
        if (t->type == GGML_TYPE_F32) {
            ggml_backend_tensor_set(t, values.data(), row * row_bytes, count * row_bytes);
        } else {
            require(ggml_is_quantized(t->type), "Unexpected initializer type");
            const size_t written = ggml_quantize_chunk(t->type, values.data(), packed.data(), 0, count, width, nullptr);
            require(written == count * row_bytes, "Quantized chunk size differs");
            ggml_backend_tensor_set(t, packed.data(), row * row_bytes, written);
        }
    }
}

struct matrix_case : test_case {
    std::string family, route;
    int rows;
    ggml_tensor * borrowed = nullptr;
    ggml_tensor * ids = nullptr;
    ggml_tensor * out = nullptr;

    matrix_case(std::string family, int rows, std::string route)
        : family(std::move(family)), route(std::move(route)), rows(rows) {
        require(this->family == "expert-down" || this->family == "expert-up" || this->family == "head", "Unknown family");
        require(rows >= 1 && rows <= 5, "Unsupported token rows");
    }
    bool head() const { return family == "head"; }
    int64_t k() const { return family == "expert-down" ? 640 : 2560; }
    int64_t m() const { return family == "expert-down" ? 2560 : head() ? 248320 : 640; }
    ggml_type weight_type() const { return head() ? GGML_TYPE_Q5_K : GGML_TYPE_Q2_0; }
    std::string vars() override {
        return "family=" + family + ",rows=" + std::to_string(rows) + ",routing=" + route;
    }
    bool use_weight_context() override { return true; }
    double max_nmse_err() override { return 5e-4; }
    ggml_tensor * build_graph(ggml_context * ctx) override { return build_graph(ctx, ctx); }
    ggml_tensor * build_graph(ggml_context * ctx, ggml_context * weights) override {
        ggml_tensor * a = borrowed ? borrowed : ggml_new_tensor_3d(weights, weight_type(), k(), m(), head() ? 1 : 512);
        ggml_set_name(a, "m5_weights");
        ggml_tensor * b = head() ? ggml_new_tensor_2d(ctx, GGML_TYPE_F32, k(), rows) :
            ggml_new_tensor_3d(ctx, GGML_TYPE_F32, k(), family == "expert-up" ? 1 : 10, rows);
        ggml_set_name(b, "m5_input");
        if (head()) {
            out = ggml_mul_mat(ctx, a, b);
        } else {
            // Match argsort_top_k's ten-row view of a 512-expert routing tensor.
            ggml_tensor * full_ids = ggml_new_tensor_2d(ctx, GGML_TYPE_I32, 512, rows);
            ggml_set_name(full_ids, "m5_ids_full");
            ids = ggml_view_2d(ctx, full_ids, 10, rows, full_ids->nb[1], 0);
            ggml_set_name(ids, "m5_ids");
            out = ggml_mul_mat_id(ctx, a, b, ids);
        }
        ggml_set_name(out, "m5_out");
        auto dims = [](const ggml_tensor * t) { return std::vector<int64_t>(t->ne, t->ne + 4); };
        json shape = {{"family", family}, {"rows", rows}, {"routing", head() ? "none" : route},
            {"type", ggml_type_name(a->type)}, {"src0", dims(a)}, {"src1", dims(b)}, {"dst", dims(out)}};
        if (ids) shape["ids_row_stride_bytes"] = ids->nb[1];
        std::fprintf(stderr, "M5_OP_SHAPE %s\n", shape.dump().c_str());
        return out;
    }
    void initialize_tensors(ggml_context * ctx) override {
        for (ggml_tensor * t = ggml_get_first_tensor(ctx); t; t = ggml_get_next_tensor(ctx, t)) {
            if (t->view_src) continue;
            if (t->type == GGML_TYPE_I32) {
                std::vector<int32_t> data(512 * rows, 0);
                auto selected = routing(rows, route, 1234);
                for (int row = 0; row < rows; ++row) std::copy_n(selected.begin()+10*row, 10, data.begin()+512*row);
                ggml_backend_tensor_set(t, data.data(), 0, data.size() * sizeof(int32_t));
            } else initialize(t);
        }
    }
    int set_routing(uint32_t seed) {
        if (!ids) return 0;
        auto data = routing(rows, route, seed);
        for (int row = 0; row < rows; ++row)
            ggml_backend_tensor_set(ids, data.data()+10*row, row*ids->nb[1], 10*sizeof(int32_t));
        return std::set<int32_t>(data.begin(), data.end()).size();
    }
};

void self_test() {
    bool wide = false;
    for (int rows = 1; rows <= 5; ++rows) {
        for (uint32_t seed = 0; seed < 100; ++seed) {
            for (const std::string mode : {"independent", "shared"}) {
                auto ids = routing(rows, mode, seed);
                for (int r = 0; r < rows; ++r) {
                    std::set<int32_t> unique(ids.begin() + 10*r, ids.begin() + 10*(r+1));
                    require(unique.size() == 10 && *unique.begin() >= 0 && *unique.rbegin() < 512, "Invalid experts");
                    if (mode == "shared") require(std::equal(ids.begin(), ids.begin()+10, ids.begin()+10*r), "Shared scenario differs");
                }
                wide |= *std::max_element(ids.begin(), ids.end()) > 400;
                require(ids == routing(rows, mode, seed), "Routing not reproducible");
            }
        }
    }
    require(wide, "Routing never reaches the full expert set");
    std::puts("M5_OP_SELF_TEST passed: 1000 routing fixtures; no backend initialized");
}

void perf(ggml_backend_t backend, const std::string & family, std::vector<int> rows, int samples) {
    ggml_init_params params = {ggml_tensor_overhead()*256 + ggml_graph_overhead_custom(1024, false)*32, nullptr, true};
    ggml_context_ptr weights(ggml_init(params)), ctx(ggml_init(params));
    matrix_case shape(family, 1, "independent");
    ggml_tensor * weight = ggml_new_tensor_3d(weights.get(), shape.weight_type(), shape.k(), shape.m(), shape.head() ? 1 : 512);
    ggml_set_name(weight, "m5_weights");
    ggml_backend_buffer_ptr weight_buf(ggml_backend_alloc_ctx_tensors(weights.get(), backend));
    require(bool(weight_buf), "Weight allocation failed");
    ggml_backend_buffer_set_usage(weight_buf.get(), GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
    initialize(weight);

    std::vector<std::unique_ptr<matrix_case>> cases;
    std::vector<ggml_cgraph *> graphs;
    for (int n : rows) {
        for (const std::string route : shape.head() || n == 1 ? std::vector<std::string>{"independent"} :
                                                              std::vector<std::string>{"independent", "shared"}) {
            auto c = std::make_unique<matrix_case>(family, n, route);
            c->borrowed = weight;
            c->build_graph(ctx.get(), weights.get());
            ggml_cgraph * graph = ggml_new_graph_custom(ctx.get(), 1024, false);
            ggml_build_forward_expand(graph, c->out);
            graphs.push_back(graph); cases.push_back(std::move(c));
        }
    }
    // Explicit cache-pressure scenario, not a claim about SSD or a guaranteed cold cache.
    ggml_tensor * scratch = ggml_new_tensor_1d(ctx.get(), GGML_TYPE_F32, 128*1024*1024/4);
    ggml_tensor * squared = ggml_sqr(ctx.get(), scratch);
    ggml_cgraph * flush_graph = ggml_new_graph_custom(ctx.get(), 1024, false);
    ggml_build_forward_expand(flush_graph, squared);
    ggml_backend_buffer_ptr input_buf(ggml_backend_alloc_ctx_tensors(ctx.get(), backend));
    require(bool(input_buf), "Input allocation failed");
    for (ggml_tensor * t = ggml_get_first_tensor(ctx.get()); t; t = ggml_get_next_tensor(ctx.get(), t)) {
        if (t->op == GGML_OP_NONE && t->type == GGML_TYPE_F32) initialize(t);
    }
    uint64_t graph_id = 0;
    auto compute = [&](ggml_cgraph * graph, json marker) {
        marker["graph"] = ++graph_id;
        marker["family"] = family;
        std::fprintf(stderr, "M5_OP_CALL %s\n", marker.dump().c_str());
        require(ggml_backend_graph_compute(backend, graph) == GGML_STATUS_SUCCESS, "GPU computation failed");
    };
    for (size_t i = 0; i < cases.size(); ++i) {
        auto & c = *cases[i];
        for (const std::string cache : {"unflushed", "pressure-128MiB"}) {
            for (int sample = -3; sample < samples; ++sample) {
                const int unique = c.set_routing(1234 + uint32_t(sample + 3));
                if (cache != "unflushed") compute(flush_graph, {{"phase", "cache-pressure"}, {"rows", c.rows}});
                compute(graphs[i], {{"phase", sample < 0 ? "warmup" : "measure"}, {"sample", sample},
                    {"rows", c.rows}, {"routing", c.head() ? "none" : c.route}, {"cache", cache}, {"unique_experts", unique}});
            }
        }
    }
    ggml_backend_synchronize(backend);
    std::fprintf(stderr, "M5_OP_DONE %s\n", json({{"family", family}, {"graphs", graph_id}, {"samples", samples},
        {"weight_bytes", ggml_nbytes(weight)}, {"scratch_input_bytes", ggml_nbytes(scratch)}}).dump().c_str());
}

int run(int argc, char ** argv) {
    if (argc == 2 && std::string(argv[1]) == "--self-test") { self_test(); return 0; }
    require(argc == 6, "Usage: probe test|perf family rows_comma samples routing");
    const std::string mode(argv[1]), family(argv[2]), route(argv[5]);
    std::vector<int> rows;
    std::stringstream input(argv[3]);
    std::string part;
    while (std::getline(input, part, ',')) {
        int n = std::stoi(part);
        require(n >= 1 && n <= 5, "Unsupported token rows"); rows.push_back(n);
    }
    require(!rows.empty(), "Missing rows");
    const int samples = std::stoi(argv[4]);
    require(samples >= 1 && samples <= 200, "Invalid sample count");
    require(mode == "test" || mode == "perf", "Unknown mode");
    if (mode == "test") require(rows.size() == 1, "Correctness uses one shape per process");
    if (mode == "perf") require(std::getenv("GGML_M5_LAB_PROFILE"), "GPU timestamps must be enabled");
    ggml_backend_load_all();
    // Retain native debug pipeline compilation records, outside measured warm samples.
    ggml_log_set(nullptr, nullptr);
    ggml_backend_ptr backend(ggml_backend_init_by_name("MTL0", nullptr));
    require(bool(backend), "MTL0 unavailable");
    if (mode == "perf") perf(backend.get(), family, rows, samples);
    else {
        ggml_backend_ptr cpu(ggml_backend_init_by_type(GGML_BACKEND_DEVICE_TYPE_CPU, nullptr));
        require(bool(cpu), "CPU reference unavailable");
        auto reg = ggml_backend_dev_backend_reg(ggml_backend_get_device(cpu.get()));
        using use_ref_t = void (*)(ggml_backend_t, bool);
        auto use_ref = reinterpret_cast<use_ref_t>(ggml_backend_reg_get_proc_address(reg, "ggml_backend_cpu_set_use_ref"));
        require(use_ref, "CPU reference selector unavailable"); use_ref(cpu.get(), true);
        matrix_case c(family, rows[0], route);
        auto printer = create_printer(CONSOLE);
        const auto status = c.eval(backend.get(), cpu.get(), nullptr, printer.get());
        const bool passed = status == test_status_t::OK;
        std::fprintf(stderr, "M5_OP_CHECK %s\n", json({{"family", family}, {"rows", rows[0]}, {"routing", route}, {"passed", passed}}).dump().c_str());
        require(passed, "CPU-reference check failed or unsupported");
    }
    return 0;
}
} // namespace m5_ops

int main(int argc, char ** argv) {
    try { return m5_ops::run(argc, argv); }
    catch (const std::exception & error) { std::fprintf(stderr, "M5_OP_ERROR %s\n", error.what()); return 1; }
}
